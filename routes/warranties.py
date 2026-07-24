from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Sale, SaleDetail, Warranty, Product, SaleClient

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
