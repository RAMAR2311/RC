from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_
from decorators import admin_required
from models import db, Sale, SaleDetail, Warranty, Product, SaleClient, Maneo, StockAdjustment

warranties_bp = Blueprint('warranties_bp', __name__)

@warranties_bp.route('/')
@login_required
def index():
    # Solo administradores (o ajusta según tu lógica de permisos)
    if current_user.rol not in ['admin', 'vendedor']:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('index'))
    
    # Listado de garantías registradas
    warranties = Warranty.query.order_by(Warranty.created_at.desc()).all()
    return render_template('warranties/index.html', warranties=warranties)

@warranties_bp.route('/api/search', methods=['GET'])
@login_required
def search_sale():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'success': False, 'message': 'Escribe un término de búsqueda.'})

    sale = None
    
    # 1. Intentar buscar por ID de Factura (número exacto)
    if query.isdigit():
        sale = Sale.query.get(int(query))

    # 2. Si no se encontró, buscar por Cédula de cliente
    if not sale:
        # Encontramos la factura más reciente asociada a esa cédula
        client = SaleClient.query.filter_by(documento=query).order_by(SaleClient.id.desc()).first()
        if client:
            sale = client.venta

    # 3. Si no se encontró, buscar por IMEI en SaleDetail (productos que tienen IMEI guardado)
    if not sale:
        # Algunos productos pueden haber sido guardados con el IMEI en 'nombre_manual' o en atributos del producto.
        # Buscamos en SaleDetail donde el producto tenga ese IMEI o el nombre incluya el IMEI.
        # Para celulares, el IMEI suele estar en el campo 'imei' del Product o en un registro especial.
        detail = SaleDetail.query.join(Product).filter(
            db.or_(
                Product.imei == query,
                Product.imei2 == query,
                SaleDetail.nombre_manual.ilike(f'%{query}%')
            )
        ).order_by(SaleDetail.id.desc()).first()
        if detail:
            sale = detail.venta

    if not sale:
        return jsonify({'success': False, 'message': 'No se encontró ninguna factura asociada a ese ID, Cédula o IMEI.'})

    # Preparar detalles de la factura
    details_data = []
    for d in sale.detalles:
        details_data.append({
            'detail_id': d.id,
            'product_id': d.product_id,
            'nombre': d.nombre_manual or (d.producto.nombre if d.producto else 'Desconocido'),
            'cantidad': d.cantidad_vendida,
            'precio': str(d.precio_venta_final)
        })

    client_doc = sale.cliente.documento if sale.cliente else 'N/A'
    client_name = sale.cliente.nombre if sale.cliente else 'N/A'

    return jsonify({
        'success': True,
        'sale': {
            'id': sale.id,
            'fecha': sale.fecha_venta.strftime('%d/%m/%Y %I:%M %p'),
            'total': str(sale.monto_total),
            'cliente_doc': client_doc,
            'cliente_nombre': client_name
        },
        'details': details_data
    })

@warranties_bp.route('/nueva', methods=['POST'])
@login_required
def create_warranty():
    sale_id = request.form.get('sale_id')
    detail_index_str = request.form.get('detail_index') # formato "product_id|nombre_manual"
    reason = request.form.get('reason', '').strip()

    if not sale_id or not detail_index_str or not reason:
        flash('Todos los campos son obligatorios.', 'danger')
        return redirect(url_for('warranties_bp.index'))

    # Parse detail
    parts = detail_index_str.split('|')
    product_id_str = parts[0]
    nombre_manual = parts[1] if len(parts) > 1 else None

    product_id = int(product_id_str) if product_id_str != 'None' else None

    warranty = Warranty()
    warranty.sale_id = sale_id
    warranty.product_id = product_id
    warranty.nombre_manual = nombre_manual
    warranty.quantity = 1
    warranty.reason = reason
    db.session.add(warranty)
    db.session.commit()

    flash('Garantía registrada exitosamente.', 'success')
    # Redirigir a la vista de impresión del ticket
    return redirect(url_for('warranties_bp.ticket', id=warranty.id))

@warranties_bp.route('/ticket/<int:id>')
@login_required
def ticket(id):
    warranty = Warranty.query.get_or_404(id)
    return render_template('warranties/ticket.html', warranty=warranty)

@warranties_bp.route('/api/update_status/<int:id>', methods=['POST'])
@login_required
def update_status(id):
    warranty = Warranty.query.get_or_404(id)
    data = request.get_json()
    new_status = data.get('status')
    admin_notes = data.get('admin_notes')
    
    if new_status:
        warranty.resolution = new_status
        if admin_notes:
            warranty.admin_notes = admin_notes
        db.session.commit()
        return jsonify({'success': True, 'message': 'Estado actualizado correctamente.'})
    
    return jsonify({'success': False, 'error': 'Estado no válido.'}), 400


@warranties_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_garantia(id):
    warranty = Warranty.query.get_or_404(id)
    try:
        db.session.delete(warranty)
        db.session.commit()
        flash('Garantía eliminada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar la garantía: {str(e)}', 'danger')
    return redirect(url_for('warranties_bp.index'))


@warranties_bp.route('/enviar-inventario/<int:id>', methods=['POST'])
@login_required
@admin_required
def enviar_inventario(id):
    warranty = Warranty.query.get_or_404(id)

    if warranty.devuelto_inventario:
        flash('Este equipo ya fue reingresado al inventario anteriormente.', 'warning')
        return redirect(url_for('warranties_bp.index'))

    if not warranty.product:
        flash('Esta garantía no tiene un producto del inventario asociado.', 'danger')
        return redirect(url_for('warranties_bp.index'))

    producto = Product.query.with_for_update().get(warranty.product.id)
    if not producto:
        flash('Producto no encontrado en la base de datos.', 'danger')
        return redirect(url_for('warranties_bp.index'))

    if producto.tipo_inventario != 'celulares' and not producto.imei:
        flash('Solo se pueden reingresar celulares del módulo de celulares.', 'warning')
        return redirect(url_for('warranties_bp.index'))

    if producto.maneo_activo:
        flash('El equipo se encuentra actualmente en un préstamo de Maneo pendiente.', 'danger')
        return redirect(url_for('warranties_bp.index'))

    if producto.cantidad_stock > 0:
        flash('El equipo ya se encuentra con stock activo en el inventario.', 'warning')
        return redirect(url_for('warranties_bp.index'))

    try:
        stock_anterior = producto.cantidad_stock
        producto.cantidad_stock = 1

        ajuste = StockAdjustment(
            product_id=producto.id,
            admin_id=current_user.id,
            tipo_movimiento=f"Reingreso por Garantía #{warranty.id}",
            stock_anterior=stock_anterior,
            stock_nuevo=1
        )
        db.session.add(ajuste)

        warranty.devuelto_inventario = True
        nota_reingreso = f"Reingresado al inventario (Garantía #{warranty.id})."
        if warranty.admin_notes:
            warranty.admin_notes = f"{warranty.admin_notes} | {nota_reingreso}"
        else:
            warranty.admin_notes = nota_reingreso

        db.session.commit()
        flash(f'Celular "{producto.nombre}" reingresado al inventario exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al reingresar el celular al inventario: {str(e)}', 'danger')

    return redirect(url_for('warranties_bp.index'))


@warranties_bp.route('/api/celulares-disponibles', methods=['GET'])
@login_required
def api_celulares_disponibles():
    q = request.args.get('q', '').strip()

    query = Product.query.filter(
        Product.tipo_inventario == 'celulares',
        Product.cantidad_stock > 0,
        ~Product.maneos.any(Maneo.estado == 'PENDIENTE')
    )

    if q:
        query = query.filter(
            or_(
                Product.nombre.ilike(f'%{q}%'),
                Product.marca.ilike(f'%{q}%'),
                Product.modelo_celular.ilike(f'%{q}%'),
                Product.imei.ilike(f'%{q}%'),
                Product.imei2.ilike(f'%{q}%'),
                Product.color.ilike(f'%{q}%'),
                Product.memoria.ilike(f'%{q}%')
            )
        )

    celulares = query.order_by(Product.fecha_creacion.desc()).limit(50).all()

    return jsonify({
        'success': True,
        'celulares': [
            {
                'id': c.id,
                'nombre': c.nombre,
                'marca': c.marca or '',
                'modelo': c.modelo_celular or '',
                'memoria': c.memoria or '',
                'color': c.color or '',
                'imei': c.imei or 'Sin IMEI',
                'inventario': c.inventario or 'Tienda',
                'precio_sugerido': float(c.precio_sugerido or 0)
            }
            for c in celulares
        ]
    })


@warranties_bp.route('/dar-cambio/<int:id>', methods=['POST'])
@login_required
@admin_required
def dar_cambio(id):
    warranty = Warranty.query.get_or_404(id)

    if warranty.replacement_product_id:
        flash('Esta garantía ya tiene un celular de cambio entregado.', 'warning')
        return redirect(url_for('warranties_bp.index'))

    replacement_id = request.form.get('replacement_product_id')
    nota_extra = request.form.get('nota_cambio', '').strip()

    if not replacement_id or not str(replacement_id).isdigit():
        flash('Debes seleccionar un celular válido del inventario.', 'danger')
        return redirect(url_for('warranties_bp.index'))

    replacement = Product.query.with_for_update().get(int(replacement_id))
    if not replacement or replacement.tipo_inventario != 'celulares':
        flash('El celular seleccionado no existe o no pertenece al inventario de celulares.', 'danger')
        return redirect(url_for('warranties_bp.index'))

    if replacement.cantidad_stock < 1 or replacement.maneo_activo:
        flash('El celular seleccionado ya no está disponible en stock.', 'danger')
        return redirect(url_for('warranties_bp.index'))

    try:
        stock_anterior = replacement.cantidad_stock
        replacement.cantidad_stock -= 1

        ajuste = StockAdjustment(
            product_id=replacement.id,
            admin_id=current_user.id,
            tipo_movimiento=f"Cambio por Garantía #{warranty.id}",
            stock_anterior=stock_anterior,
            stock_nuevo=replacement.cantidad_stock
        )
        db.session.add(ajuste)

        warranty.replacement_product_id = replacement.id
        warranty.resolution = 'Entregada'

        imei_txt = f" (IMEI: {replacement.imei})" if replacement.imei else ""
        nota_cambio = f"Cambio entregado: {replacement.nombre}{imei_txt}"
        if nota_extra:
            nota_cambio = f"{nota_cambio} - {nota_extra}"

        if warranty.admin_notes:
            warranty.admin_notes = f"{warranty.admin_notes} | {nota_cambio}"
        else:
            warranty.admin_notes = nota_cambio

        db.session.commit()
        flash(f'Celular de cambio "{replacement.nombre}" entregado y descontado del inventario.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al entregar celular de cambio: {str(e)}', 'danger')

    return redirect(url_for('warranties_bp.index'))
