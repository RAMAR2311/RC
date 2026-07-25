from flask import Blueprint, request, jsonify, flash, redirect, render_template, abort, url_for
from flask_login import login_required, current_user
from models import db, Product, ProductVariant, Sale, SaleDetail, SalePayment, SaleClient, Expense, Retoma, obtener_hora_bogota, PriceApproval, Asesor
from decorators import admin_required
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

sales_bp = Blueprint('sales_bp', __name__)

@sales_bp.route('/nueva', methods=['GET', 'POST'])
@login_required # Importante: Te bloqueará el acceso si no hay current_user logeado (Flask-Login)
def procesar_venta():
    if request.method == 'GET':
        asesores = Asesor.query.filter_by(activo=True).order_by(Asesor.nombre).all()
        return render_template('sales/nueva.html', asesores=asesores)

    """
    Se espera que los datos vengan en el cuerpo de la petición (JSON)
    Ej: {'items': [{ 'product_id': 1, 'cantidad': 2, 'precio_final': 15.50}, ...], 'metodo_pago': 'transferencia'}
    """
    data = request.get_json()
    items = data.get('items', [])
    pagos_data = data.get('pagos', [])  # Nuevo: array de pagos mixtos
    metodo_pago_legacy = data.get('metodo_pago', 'efectivo')  # Retrocompatibilidad
    asesor_id = data.get('asesor_id')
    
    if not items:
        return jsonify({'error': 'No se enviaron productos para la venta'}), 400

    # Si no se envían pagos en el nuevo formato, crear uno único con el método legacy
    if not pagos_data:
        pagos_data = [{'metodo_pago': metodo_pago_legacy, 'monto': None}]  # monto=None se llenará con el total

    try:
        # Determinar el método de pago principal (para la columna legacy de retrocompatibilidad)
        if len(pagos_data) == 1:
            metodo_pago_principal = pagos_data[0].get('metodo_pago', 'efectivo')
        else:
            metodo_pago_principal = 'mixto'

        # Manejar Fecha de Venta para registros de fechas anteriores
        fecha_venta_str = data.get('fecha_venta')
        fecha_venta_obj = obtener_hora_bogota()
        if fecha_venta_str:
            try:
                fecha_seleccionada = datetime.strptime(fecha_venta_str, '%Y-%m-%d').date()
                if fecha_seleccionada != fecha_venta_obj.date():
                    # Si no es hoy, combinamos la fecha seleccionada con la hora actual para conservar secuencialidad de hora de registro
                    fecha_venta_obj = datetime.combine(fecha_seleccionada, fecha_venta_obj.time())
            except ValueError:
                pass # Fallback silencioso a la hora actual si el formato falla

        # Validar tipo de venta (Celulares vs General) y evitar mezcla
        tipo_venta_detectado = None
        for item in items:
            es_manual = item.get('es_manual', False)
            precio_venta_final = Decimal(str(item.get('precio_final', '0.00')))
            variant_id = item.get('variant_id')

            if es_manual:
                tipo_item = 'general'
            else:
                prod_id = item.get('product_id')
                producto_check = Product.query.get(prod_id)
                if not producto_check:
                    return jsonify({'error': f"El producto con ID {prod_id} no existe."}), 400
                
                # Validar precio mínimo y consultar aprobaciones remotas si es menor
                if current_user.rol != 'admin' and precio_venta_final < producto_check.precio_minimo:
                    aprobacion = PriceApproval.query.filter_by(
                        vendedor_id=current_user.id,
                        product_id=prod_id,
                        variant_id=variant_id,
                        estado='aprobado'
                    ).filter(PriceApproval.precio_aprobado <= precio_venta_final).first()
                    
                    if not aprobacion:
                        return jsonify({'error': f'El precio de {producto_check.nombre} (${precio_venta_final}) es inferior al mínimo permitido y no tiene aprobación remota válida.'}), 400
                    else:
                        # Marcar la aprobación como 'completada'
                        aprobacion.estado = 'completada'
                
                tipo_item = 'celulares' if producto_check.tipo_inventario == 'celulares' else 'general'
            
            if tipo_venta_detectado is None:
                tipo_venta_detectado = tipo_item
            elif tipo_venta_detectado != tipo_item:
                return jsonify({'error': 'No se pueden mezclar celulares con accesorios en la misma venta. Por favor, realice transacciones separadas para no descuadrar los arqueos.'}), 400
        
        tipo_venta_detectado = tipo_venta_detectado or 'general'

        nueva_venta = Sale(
            vendedor_id=current_user.id,
            asesor_id=asesor_id,
            monto_total=Decimal('0.00'),
            metodo_pago=metodo_pago_principal,
            fecha_venta=fecha_venta_obj,
            tipo_venta=tipo_venta_detectado,
            sucursal=current_user.sucursal
        )
        db.session.add(nueva_venta)
        db.session.flush()

        monto_total = Decimal('0.00')

        for item in items:
            product_id = item.get('product_id')
            variant_id = item.get('variant_id') # Posible variante
            cantidad_vendida = int(item.get('cantidad', 0))
            precio_venta_final = Decimal(str(item.get('precio_final', '0.00')))
            es_manual = item.get('es_manual', False)
            es_obsequio = item.get('es_obsequio', False)

            if cantidad_vendida <= 0:
                raise ValueError("La cantidad vendida debe ser mayor a 0.")

            if es_manual:
                # Producto manual (prestado de otro local) — no descuenta stock
                nombre_manual = item.get('nombre_manual', 'Producto Externo')
                precio_costo_manual = Decimal(str(item.get('precio_costo', '0.00')))

                detalle = SaleDetail(
                    sale_id=nueva_venta.id,
                    product_id=None,
                    variant_id=None,
                    cantidad_vendida=cantidad_vendida,
                    precio_venta_final=precio_venta_final,
                    nombre_manual=nombre_manual,
                    precio_costo_manual=precio_costo_manual
                )
                db.session.add(detalle)
                monto_total += (precio_venta_final * cantidad_vendida)

                # Crear el gasto automático para descontar el ingreso prestado del balance final
                if precio_costo_manual > 0:
                    gasto_externo = Expense(
                        usuario_id=current_user.id,
                        tipo_gasto='Gasto Diario',
                        categoria='Pago Prod. Externo',
                        descripcion=f"Pago por producto manual prestado: {nombre_manual}",
                        monto=(precio_costo_manual * cantidad_vendida),
                        fecha_gasto=fecha_venta_obj,
                        sucursal=current_user.sucursal
                    )
                    db.session.add(gasto_externo)
            else:
                # Producto del inventario propio
                producto = Product.query.with_for_update().get(product_id)
                
                if not producto:
                    raise ValueError(f"El producto con ID {product_id} no existe.")

                if variant_id:
                    variante = ProductVariant.query.with_for_update().get(variant_id)
                    if not variante:
                        raise ValueError(f"La variante con ID {variant_id} no existe.")
                    if cantidad_vendida > variante.cantidad_stock:
                        raise ValueError(f"Stock insuficiente para la variante '{variante.nombre_variante}' de '{producto.nombre}'. Solicitado: {cantidad_vendida}, Disponible: {variante.cantidad_stock}.")
                    
                    stock_anterior = variante.cantidad_stock
                    variante.cantidad_stock -= cantidad_vendida
                    producto.cantidad_stock -= cantidad_vendida # Sincronizar producto base
                    precio_limite_autorizado = variante.precio_costo if current_user.rol == 'admin' else variante.precio_minimo
                    
                    from models import StockAdjustment
                    ajuste = StockAdjustment(
                        product_id=producto.id,
                        admin_id=current_user.id,
                        tipo_movimiento=f"Venta Tienda (Subcat: {variante.nombre_variante})",
                        stock_anterior=stock_anterior,
                        stock_nuevo=variante.cantidad_stock
                    )
                    db.session.add(ajuste)
                else:
                    if cantidad_vendida > producto.cantidad_stock:
                        raise ValueError(f"Stock insuficiente para el producto '{producto.nombre}'. Solicitado: {cantidad_vendida}, Disponible: {producto.cantidad_stock}.")
                    
                    stock_anterior = producto.cantidad_stock
                    producto.cantidad_stock -= cantidad_vendida
                    precio_limite_autorizado = producto.precio_costo if current_user.rol == 'admin' else producto.precio_minimo
                    
                    from models import StockAdjustment
                    ajuste = StockAdjustment(
                        product_id=producto.id,
                        admin_id=current_user.id,
                        tipo_movimiento="Venta Tienda",
                        stock_anterior=stock_anterior,
                        stock_nuevo=producto.cantidad_stock
                    )
                    db.session.add(ajuste)

                if not es_obsequio and precio_venta_final < precio_limite_autorizado:
                    raise ValueError(f"No autorizado: El precio ({precio_venta_final}) del producto '{producto.nombre}' está por debajo del límite permitido ({precio_limite_autorizado}).")

                detalle = SaleDetail(
                    sale_id=nueva_venta.id,
                    product_id=producto.id,
                    variant_id=variant_id,
                    cantidad_vendida=cantidad_vendida,
                    precio_venta_final=precio_venta_final
                )
                db.session.add(detalle)
                db.session.flush() # Importante para tener el id de la venta si se quisiera, pero ya lo tenemos en nueva_venta.id
                
                # Para añadir el ID de la venta al tipo de movimiento ahora que la venta tiene ID asignado:
                ajuste.tipo_movimiento = f"{ajuste.tipo_movimiento} #{nueva_venta.id}"
                
                monto_total += (precio_venta_final * cantidad_vendida)

        # Manejar información de Retoma (ahora es un descuento sobre el monto total)
        retoma_info = data.get('retoma_data')
        monto_retoma = Decimal('0.00')
        if retoma_info:
            monto_retoma = Decimal(str(retoma_info.get('valor_retoma', 0)))
            if monto_retoma <= 0:
                raise ValueError("El monto acreditado por la retoma debe ser mayor a 0.")
            monto_total = max(Decimal('0.00'), monto_total - monto_retoma)

        nueva_venta.monto_total = monto_total

        # Registrar los pagos mixtos en la tabla sale_payments
        total_pagos = Decimal('0.00')
        for pago_info in pagos_data:
            metodo = pago_info.get('metodo_pago', 'efectivo')
            monto_pago = pago_info.get('monto')
            
            if monto_pago is None:
                # Si solo hay un pago sin monto explícito, asignar el total completo
                monto_pago = monto_total
            else:
                monto_pago = Decimal(str(monto_pago))
            
            if monto_pago <= 0:
                if monto_total == 0:
                    continue # Salto el pago si el total a pagar es 0 (ej. cubierto 100% por retoma)
                raise ValueError(f"El monto del pago por '{metodo}' debe ser mayor a 0.")
            
            pago = SalePayment(
                sale_id=nueva_venta.id,
                metodo_pago=metodo,
                monto=monto_pago
            )
            db.session.add(pago)
            total_pagos += monto_pago

        # Validar que la suma de pagos cubra el total de la venta
        if total_pagos != monto_total:
            raise ValueError(f"La suma de los pagos (${total_pagos}) no coincide con el total de la venta (${monto_total}). Diferencia: ${monto_total - total_pagos}.")

        # Crear el registro de Retoma si aplica
        if retoma_info:
            # Note: Retoma expects usuario_id, not vendedor_id (as defined in models.py)
            retoma_registro = Retoma(
                sale_id=nueva_venta.id,
                modelo=retoma_info.get('modelo', '').strip(),
                marca=retoma_info.get('marca', '').strip(),
                proveedor='Cliente',
                valor_retoma=monto_retoma,
                imei1=retoma_info.get('imei1', '').strip(),
                imei2=retoma_info.get('imei2', '').strip(),
                color=retoma_info.get('color', '').strip(),
                bateria=retoma_info.get('bateria', '').strip(),
                memoria=retoma_info.get('memoria', '').strip(),
                observaciones=retoma_info.get('observaciones', '').strip(),
                vendedor_id=current_user.id
            )
            
            if not retoma_registro.modelo or not retoma_registro.imei1:
                raise ValueError("El modelo y el IMEI 1 son obligatorios para la retoma.")
                
            db.session.add(retoma_registro)

        cliente_data = data.get('cliente')
        if cliente_data and isinstance(cliente_data, dict):
            cliente = SaleClient(
                sale_id=nueva_venta.id,
                nombre=cliente_data.get('nombre', 'Desconocido').strip(),
                documento=cliente_data.get('documento', '0').strip(),
                telefono=cliente_data.get('telefono', '').strip(),
                email=cliente_data.get('email', '').strip() if cliente_data.get('email') else None,
                direccion=cliente_data.get('direccion', '').strip() if cliente_data.get('direccion') else None
            )
            db.session.add(cliente)

        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Venta registrada e inventario descontado con éxito.',
            'sale_id': nueva_venta.id,
            'total': str(monto_total)
        }), 201

    except ValueError as val_err:
        db.session.rollback()
        return jsonify({'error': str(val_err)}), 400
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Ocurrió un error interno al procesar la venta.'}), 500

# Endpoint API asíncrono para el escáner del Punto de Venta
@sales_bp.route('/api/producto/<path:sku>', methods=['GET'])
@login_required
def api_buscar_producto(sku):
    producto = Product.query.filter(
        Product.tipo_inventario.in_(['tienda', 'celulares', 'externos']),
        or_(
            Product.sku == sku,
            Product.imei == sku,
            Product.imei2 == sku
        )
    ).first()
    auto_select_variant = None
    
    if not producto:
        # Búsqueda por IMEI en variantes de celulares
        variante = ProductVariant.query.join(Product).filter(
            Product.tipo_inventario == 'celulares',
            ProductVariant.nombre_variante.like(f"%{sku}%")
        ).first()
        
        if variante:
            producto = variante.producto
            auto_select_variant = variante.id
        else:
            return jsonify({'error': 'Código SKU o IMEI no encontrado en el sistema'}), 404
        
    return jsonify({
        'id': producto.id,
        'nombre': producto.nombre,
        'sku': producto.sku,
        'tipo_inventario': producto.tipo_inventario,
        'cantidad_stock': producto.total_stock,
        'precio_minimo': float(producto.precio_minimo),
        'precio_limite': float(producto.precio_costo) if current_user.rol == 'admin' else float(producto.precio_minimo),
        'precio_sugerido': float(producto.precio_sugerido),
        'variantes': [{"id": v.id, "nombre": v.nombre_variante, "stock": v.cantidad_stock, "precio_minimo": float(v.precio_minimo or producto.precio_minimo), "precio_limite": float(v.precio_costo or producto.precio_costo) if current_user.rol == 'admin' else float(v.precio_minimo or producto.precio_minimo), "precio_sugerido": float(v.precio_sugerido or producto.precio_sugerido)} for v in producto.variantes],
        'auto_select_variant': auto_select_variant
    })

# Ruta para la Impresión del formato Térmico (Ticket)
@sales_bp.route('/recibo/<int:sale_id>', methods=['GET'])
@login_required # Proteger confidencialidad del cajero
def imprimir_ticket(sale_id):
    # Regla: Retorna 404 si alguien ingresa un ID falso
    venta = Sale.query.get_or_404(sale_id)
    return render_template('sales/ticket.html', venta=venta)

# Endpoint Historial de Ventas (Administradores)
@sales_bp.route('/historial', methods=['GET'])
@login_required
@admin_required
def historial():
    # Calcular el valor exacto de 'HOY' en Bogotá
    hoy_bogota = obtener_hora_bogota().strftime('%Y-%m-%d')
    
    # Si existen los args, los usa, de lo contrario colapsa a HOY por defecto
    fecha_inicio = request.args.get('fecha_inicio', hoy_bogota)
    fecha_fin = request.args.get('fecha_fin', hoy_bogota)
    
    # Optimización: eager loading (evita N+1 con joinedload)
    query = Sale.query.options(joinedload(Sale.vendedor))
    
    # Motor de búsqueda por Rango Restricto
    if fecha_inicio:
        inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
        query = query.filter(Sale.fecha_venta >= inicio_dt)
        
    if fecha_fin:
        fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
        # Sumar 1 día matemáticamente para incluir los registros hasta las 23:59:59 del último día
        query = query.filter(Sale.fecha_venta < fin_dt + timedelta(days=1))
        
    ventas = query.order_by(Sale.fecha_venta.desc()).all()
    
    # Auditar y cruzar sumatorios de métricas de pago
    # Sistema híbrido: usa SalePayment si existe, caso contrario cae al metodo_pago legacy
    total_efectivo = Decimal('0')
    total_bancolombia = Decimal('0')
    total_daviplata = Decimal('0')
    total_tarjeta_credito = Decimal('0')
    total_addi = Decimal('0')
    total_sitecredito = Decimal('0')
    total_otros = Decimal('0')  # Para retomas, nequi viejo, etc.
    total_retomas = Decimal('0')
    total_mixto = 0  # Contador de ventas con pago mixto

    for v in ventas:
        if v.pagos:  # Pagos nuevos con tabla sale_payments
            for pago in v.pagos:
                if pago.metodo_pago == 'efectivo':
                    total_efectivo += pago.monto
                elif pago.metodo_pago == 'bancolombia':
                    total_bancolombia += pago.monto
                elif pago.metodo_pago == 'daviplata':
                    total_daviplata += pago.monto
                elif pago.metodo_pago == 'tarjeta_credito':
                    total_tarjeta_credito += pago.monto
                elif pago.metodo_pago == 'addi':
                    total_addi += pago.monto
                elif pago.metodo_pago == 'sitecredito':
                    total_sitecredito += pago.monto
                else:
                    total_otros += pago.monto
            if len(v.pagos) > 1:
                total_mixto += 1
        else:  # Retrocompatibilidad con ventas antiguas sin SalePayment
            if v.metodo_pago == 'efectivo':
                total_efectivo += v.monto_total
            elif v.metodo_pago == 'bancolombia':
                total_bancolombia += v.monto_total
            elif v.metodo_pago == 'daviplata':
                total_daviplata += v.monto_total
            elif v.metodo_pago == 'tarjeta_credito':
                total_tarjeta_credito += v.monto_total
            elif v.metodo_pago == 'addi':
                total_addi += v.monto_total
            elif v.metodo_pago == 'sitecredito':
                total_sitecredito += v.monto_total
            else:
                total_otros += v.monto_total

    # Envío al Engine de HTML
    return render_template('sales/historial.html', 
                           ventas=ventas, 
                           total_efectivo=total_efectivo,
                           total_bancolombia=total_bancolombia,
                           total_daviplata=total_daviplata,
                           total_tarjeta_credito=total_tarjeta_credito,
                           total_addi=total_addi,
                           total_sitecredito=total_sitecredito,
                           total_otros=total_otros,
                           total_mixto=total_mixto,
                           fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin)


# Endpoint Visor de Ventas del Día para Cajeros (Solo lectura, se resetea cada día)
@sales_bp.route('/ventas_hoy', methods=['GET'])
@login_required
def ventas_hoy():
    # Obtener la fecha de hoy
    hoy_bogota = obtener_hora_bogota().date()
    # Para la consulta requerimos abarcar desde las 00:00:00 hasta las 23:59:59
    inicio_dt = datetime.combine(hoy_bogota, datetime.min.time())
    fin_dt = datetime.combine(hoy_bogota, datetime.max.time())
    
    # Consultar todas las ventas de este día (sin importar si es admin o vendedor)
    query = Sale.query.options(joinedload(Sale.vendedor)).filter(
        Sale.fecha_venta >= inicio_dt,
        Sale.fecha_venta <= fin_dt
    )
    
    # Si no es admin, solo ve sus propias ventas
    if current_user.rol != 'admin':
        query = query.filter(Sale.vendedor_id == current_user.id)
        
    ventas = query.order_by(Sale.fecha_venta.desc()).all()
    
    # Acumuladores de las ventas de hoy
    total_efectivo = Decimal('0')
    total_transferencias = Decimal('0')
    total_mixto = 0
    
    for v in ventas:
        if v.pagos:
            for pago in v.pagos:
                if pago.metodo_pago == 'efectivo':
                    total_efectivo += pago.monto
                else: 
                    total_transferencias += pago.monto
            if len(v.pagos) > 1:
                total_mixto += 1
        else:
            if v.metodo_pago == 'efectivo':
                total_efectivo += v.monto_total
            else:
                total_transferencias += v.monto_total
                
    return render_template('sales/ventas_hoy.html',
                           ventas=ventas,
                           total_efectivo=total_efectivo,
                           total_transferencias=total_transferencias,
                           total_mixto=total_mixto,
                           hoy=hoy_bogota.strftime('%Y-%m-%d'))


# Endpoint para Anular/Eliminar Venta Histórica
@sales_bp.route('/eliminar/<int:sale_id>', methods=['POST'])
@login_required
@admin_required
def eliminar_venta(sale_id):
    venta = Sale.query.get_or_404(sale_id)
    
    try:
        # Revertir Stock
        from models import StockAdjustment
        for detalle in venta.detalles:
            if detalle.variant_id:
                variante = ProductVariant.query.with_for_update().get(detalle.variant_id)
                if variante:
                    stock_anterior = variante.cantidad_stock
                    variante.cantidad_stock += detalle.cantidad_vendida
                    
                    ajuste = StockAdjustment(
                        product_id=detalle.product_id,
                        admin_id=current_user.id,
                        tipo_movimiento=f"Anulación Venta #{venta.id} (Subcat: {variante.nombre_variante})",
                        stock_anterior=stock_anterior,
                        stock_nuevo=variante.cantidad_stock
                    )
                    db.session.add(ajuste)
                    
                producto = Product.query.with_for_update().get(detalle.product_id)
                if producto:
                    producto.cantidad_stock += detalle.cantidad_vendida
            elif detalle.product_id:
                producto = Product.query.with_for_update().get(detalle.product_id)
                if producto:
                    stock_anterior = producto.cantidad_stock
                    producto.cantidad_stock += detalle.cantidad_vendida
                    
                    ajuste = StockAdjustment(
                        product_id=producto.id,
                        admin_id=current_user.id,
                        tipo_movimiento=f"Anulación Venta #{venta.id}",
                        stock_anterior=stock_anterior,
                        stock_nuevo=producto.cantidad_stock
                    )
                    db.session.add(ajuste)
                    
        # Verificar y eliminar Retomas asociadas
        if hasattr(venta, 'retomas_asociadas') and venta.retomas_asociadas:
            for retoma in venta.retomas_asociadas:
                if retoma.estado == 'aprobado':
                    raise ValueError("No se puede anular la venta porque tiene una retoma asociada que ya fue aprobada e ingresada al inventario.")
                db.session.delete(retoma)

        # Eliminar Venta y Detalles (Cascada)
        db.session.delete(venta)
        db.session.commit()
        flash('Venta anulada y stock devuelto exitosamente.', 'success')
        
    except ValueError as ve:
        db.session.rollback()
        flash(str(ve), 'warning')
    except Exception as e:
        db.session.rollback()
        flash('Ocurrió un error al anular la venta.', 'danger')
        
    return redirect(url_for('sales_bp.historial'))

# Endpoint Catálogo Estricto de solo vista para Operarios
@sales_bp.route('/catalogo', methods=['GET'])
@login_required 
def catalogo():
    query_str = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    
    base_query = Product.query.filter(
        Product.tipo_inventario.in_(['tienda', 'celulares']),
        Product.cantidad_stock > 0
    )
    
    if query_str:
        # Motor de similitud Case-Insensitive (Like)
        search_term = f"%{query_str}%"
        base_query = base_query.filter(
            or_(
                Product.sku.ilike(search_term), 
                Product.nombre.ilike(search_term)
            )
        )
        
    paginacion = base_query.order_by(Product.nombre).paginate(page=page, per_page=20, error_out=False)
        
    return render_template('sales/catalogo.html', productos=paginacion.items, paginacion=paginacion, q=query_str)

@sales_bp.route('/caja_visual', methods=['GET'])
@login_required
def caja_visual():
    from models import obtener_hora_bogota
    hoy_bogota = obtener_hora_bogota()
    productos_query = Product.query.filter(Product.tipo_inventario.in_(['tienda', 'celulares'])).order_by(Product.nombre.asc()).all()
    
    # Filtrar para mostrar solo los que tienen stock
    productos = [p for p in productos_query if p.total_stock > 0]
    
    asesores = Asesor.query.filter_by(activo=True).order_by(Asesor.nombre).all()
    
    return render_template('sales/caja_visual.html', productos=productos, asesores=asesores, hoy=hoy_bogota.strftime('%Y-%m-%d'))

