from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, send_file
from flask_login import login_required, current_user
from models import db, Product, Sale, SaleDetail, SalePayment, ProductVariant
from decorators import admin_required
from datetime import datetime
import pytz
import os
from werkzeug.utils import secure_filename
from decimal import Decimal
from models import db, Product, Sale, SaleDetail, SalePayment, ProductVariant, ArqueoCaja

celulares_bp = Blueprint('celulares_bp', __name__)

def obtener_hora_bogota():
    return datetime.now(pytz.timezone('America/Bogota')).replace(tzinfo=None)

@celulares_bp.route('/inventario')
@login_required
def inventario():
    q = request.args.get('q', '').strip()
    estado = request.args.get('estado', 'activos').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Query for all celulares to calculate KPIs
    todos_celulares = Product.query.filter_by(tipo_inventario='celulares').all()
    
    stock_activo = 0
    costo_total = 0.0
    ventas_estimadas = 0.0
    
    for c in todos_celulares:
        if c.cantidad_stock > 0:
            stock_activo += c.cantidad_stock
            costo_total += float(c.precio_costo) * c.cantidad_stock
            ventas_estimadas += float(c.precio_sugerido) * c.cantidad_stock

    # Base query for table
    base_query = Product.query.filter_by(tipo_inventario='celulares')

    if estado == 'activos':
        base_query = base_query.filter(Product.cantidad_stock > 0)
    elif estado == 'vendidos':
        base_query = base_query.filter(Product.cantidad_stock == 0)

    if q:
        from sqlalchemy import or_
        base_query = base_query.filter(
            or_(
                Product.marca.ilike(f'%{q}%'),
                Product.modelo_celular.ilike(f'%{q}%'),
                Product.imei.ilike(f'%{q}%'),
                Product.imei2.ilike(f'%{q}%'),
                Product.proveedor.ilike(f'%{q}%'),
            )
        )

    paginacion = base_query.order_by(Product.fecha_creacion.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('celulares/inventario.html', 
                           celulares=paginacion.items,
                           paginacion=paginacion,
                           q=q,
                           estado=estado,
                           stock_activo=stock_activo,
                           costo_total=costo_total,
                           ventas_estimadas=ventas_estimadas)


@celulares_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo_celular():
    if request.method == 'POST':
        marca = request.form.get('marca', '').strip()
        modelo_celular = request.form.get('modelo_celular', '').strip()
        color = request.form.get('color', '').strip()
        bateria = request.form.get('bateria', '').strip()
        memoria = request.form.get('memoria', '').strip()
        imei = request.form.get('imei', '').strip()
        imei2 = request.form.get('imei2', '').strip()
        proveedor = request.form.get('proveedor', '').strip()
        
        precio_costo_str = request.form.get('precio_costo', '0').replace(',', '')
        precio_sugerido_str = request.form.get('precio_sugerido', '0').replace(',', '')
        precio_minimo_str = request.form.get('precio_minimo', '0').replace(',', '')
        
        nombre_completo = f"Celular {marca} {modelo_celular} {color} {memoria}".strip()
        sku_base = f"CEL-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        imagen_filename = None
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                upload_folder = current_app.config['UPLOAD_FOLDER']
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                file.save(os.path.join(upload_folder, filename))
                imagen_filename = filename
        
        nuevo = Product(
            nombre=nombre_completo,
            sku=sku_base,
            tipo_inventario='celulares',
            cantidad_stock=1, # Siempre 1 porque es un registro único
            precio_costo=float(precio_costo_str) if precio_costo_str else 0.0,
            precio_minimo=float(precio_minimo_str) if precio_minimo_str else 0.0,
            precio_sugerido=float(precio_sugerido_str) if precio_sugerido_str else 0.0,
            marca=marca,
            modelo_celular=modelo_celular,
            color=color,
            bateria=bateria,
            memoria=memoria,
            imei=imei,
            imei2=imei2,
            proveedor=proveedor,
            imagen=imagen_filename
        )
        
        try:
            db.session.add(nuevo)
            db.session.commit()
            flash('Celular ingresado al inventario exitosamente.', 'success')
            return redirect(url_for('celulares_bp.inventario'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar el celular: {str(e)}', 'danger')

    return render_template('celulares/form_celular.html', celular=None)

@celulares_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_celular(id):
    celular = Product.query.get_or_404(id)
    if celular.tipo_inventario != 'celulares':
        flash('El producto seleccionado no es un celular.', 'danger')
        return redirect(url_for('celulares_bp.inventario'))
        
    if request.method == 'POST':
        celular.marca = request.form.get('marca', '').strip()
        celular.modelo_celular = request.form.get('modelo_celular', '').strip()
        celular.color = request.form.get('color', '').strip()
        celular.bateria = request.form.get('bateria', '').strip()
        celular.memoria = request.form.get('memoria', '').strip()
        celular.imei = request.form.get('imei', '').strip()
        celular.imei2 = request.form.get('imei2', '').strip()
        celular.proveedor = request.form.get('proveedor', '').strip()
        
        celular.nombre = f"Celular {celular.marca} {celular.modelo_celular} {celular.color} {celular.memoria}".strip()
            
        precio_costo_str = request.form.get('precio_costo', '0').replace(',', '')
        precio_sugerido_str = request.form.get('precio_sugerido', '0').replace(',', '')
        precio_minimo_str = request.form.get('precio_minimo', '0').replace(',', '')
        
        celular.precio_costo = float(precio_costo_str) if precio_costo_str else 0.0
        celular.precio_minimo = float(precio_minimo_str) if precio_minimo_str else 0.0
        celular.precio_sugerido = float(precio_sugerido_str) if precio_sugerido_str else 0.0
        
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                upload_folder = current_app.config['UPLOAD_FOLDER']
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                file.save(os.path.join(upload_folder, filename))
                celular.imagen = filename
            
        try:
            db.session.commit()
            flash('Celular actualizado exitosamente.', 'success')
            return redirect(url_for('celulares_bp.inventario'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar: {str(e)}', 'danger')
            
    return render_template('celulares/form_celular.html', celular=celular)

@celulares_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_celular(id):
    celular = Product.query.get_or_404(id)
    if celular.tipo_inventario != 'celulares':
        flash('No es un celular', 'danger')
        return redirect(url_for('celulares_bp.inventario'))
        
    if celular.detalles_venta:
        flash('No se puede eliminar porque ya tiene ventas asociadas.', 'danger')
        return redirect(url_for('celulares_bp.inventario'))
        
    
    try:
        db.session.delete(celular)
        db.session.commit()
        flash('Modelo de celular eliminado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el modelo: {str(e)}', 'danger')
        
    return redirect(url_for('celulares_bp.inventario'))

@celulares_bp.route('/clientes')
@login_required
@admin_required
def clientes():
    from models import SaleClient
    # Subconsulta para obtener el ID de registro más reciente para cada documento único
    subquery = db.session.query(
        db.func.max(SaleClient.id)
    ).group_by(SaleClient.documento).subquery()
    
    # Obtener los clientes correspondientes a esos IDs ordenados por nombre
    clientes_lista = SaleClient.query.filter(
        SaleClient.id.in_(subquery)
    ).order_by(SaleClient.nombre).all()
    
    return render_template('celulares/clientes.html', clientes=clientes_lista)

@celulares_bp.route('/clientes/detalle/<documento>')
@login_required
@admin_required
def detalle_cliente(documento):
    from models import SaleClient, SaleDetail, SalePayment
    # All sales for this client document
    registros = db.session.query(SaleClient, SaleDetail)\
        .join(Sale, SaleClient.sale_id == Sale.id)\
        .join(SaleDetail, Sale.id == SaleDetail.sale_id)\
        .filter(SaleClient.documento == documento)\
        .order_by(SaleClient.id.desc()).all()
    if not registros:
        flash('Cliente no encontrado.', 'warning')
        return redirect(url_for('celulares_bp.clientes'))
    cliente_info = registros[0][0]  # First SaleClient record for name/phone
    return render_template('celulares/detalle_cliente.html',
                           cliente=cliente_info,
                           registros=registros)

@celulares_bp.route('/api/cliente/buscar')
@login_required
def api_buscar_cliente():
    from models import SaleClient
    documento = request.args.get('documento', '').strip()
    if not documento:
        return jsonify({'encontrado': False})
    cliente = SaleClient.query.filter_by(documento=documento).order_by(SaleClient.id.desc()).first()
    if cliente:
        return jsonify({
            'encontrado': True, 
            'nombre': cliente.nombre, 
            'telefono': cliente.telefono,
            'email': cliente.email or '',
            'direccion': cliente.direccion or ''
        })
    return jsonify({'encontrado': False})

@celulares_bp.route('/venta', methods=['GET', 'POST'])
@login_required
def venta():
    # Mostrar solo celulares que están en stock
    celulares_disponibles = Product.query.filter(
        Product.tipo_inventario == 'celulares',
        Product.cantidad_stock > 0
    ).all()
    
    if request.method == 'POST':
        celular_id = request.form.get('celular_id')
        precio_venta_final = float(request.form.get('precio_venta_final', 0.0))
        
        # Pagos mixtos
        metodos_pago = request.form.getlist('metodo_pago[]')
        montos_pago = request.form.getlist('monto_pago[]')
        
        if not celular_id or not metodos_pago or not montos_pago:
            flash('Datos incompletos para la venta.', 'danger')
            return redirect(url_for('celulares_bp.venta'))
            
        celular = Product.query.get(celular_id)
        if not celular or celular.cantidad_stock < 1:
            flash('El celular seleccionado no está disponible en stock.', 'danger')
            return redirect(url_for('celulares_bp.venta'))
            
        if precio_venta_final < float(celular.precio_minimo) and current_user.rol != 'admin':
            flash(f'El precio de venta no puede ser menor al mínimo permitido (${celular.precio_minimo:,.2f}).', 'danger')
            return redirect(url_for('celulares_bp.venta'))
            
        # Crear la Venta General (Se registrará en cajas)
        nueva_venta = Sale(
            vendedor_id=current_user.id,
            monto_total=precio_venta_final,
            # metode_pago is legacy, we can put the primary one or 'mixto'
            metodo_pago=metodos_pago[0] if len(metodos_pago) == 1 else 'mixto',
            tipo_venta='celulares'
        )
        db.session.add(nueva_venta)
        db.session.flush()
        
        # Registrar pagos
        suma_pagos = 0.0
        for mp, monto in zip(metodos_pago, montos_pago):
            monto_float = float(monto)
            if monto_float > 0:
                pago = SalePayment(
                    sale_id=nueva_venta.id,
                    metodo_pago=mp,
                    monto=monto_float
                )
                db.session.add(pago)
                suma_pagos += monto_float
                
        if abs(suma_pagos - precio_venta_final) > 0.01:
            db.session.rollback()
            flash('La suma de los métodos de pago no coincide con el total de la venta.', 'danger')
            return redirect(url_for('celulares_bp.venta'))
            
        # Registrar detalle
        detalle = SaleDetail(
            sale_id=nueva_venta.id,
            product_id=celular.id,
            cantidad_vendida=1,
            precio_venta_final=precio_venta_final
        )
        db.session.add(detalle)
        
        # Descontar stock
        celular.cantidad_stock -= 1
        
        try:
            db.session.commit()
            flash('Venta de celular registrada exitosamente.', 'success')
            return redirect(url_for('celulares_bp.historial_ventas'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar la venta: {str(e)}', 'danger')
            
    return render_template('celulares/venta.html', celulares=celulares_disponibles)

@celulares_bp.route('/ventas/historial')
@login_required
def historial_ventas():
    # Obtener las ventas donde haya al menos un detalle de un producto tipo 'celulares'
    ventas_celulares = Sale.query.join(SaleDetail).join(Product).filter(
        Product.tipo_inventario == 'celulares'
    ).order_by(Sale.fecha_venta.desc()).all()
    
    # Para la vista, queremos mostrar datos específicos
    datos_historial = []
    for v in ventas_celulares:
        # En caso de ventas mixtas, filtramos solo los detalles de celulares (aunque usualmente será 1)
        detalles_cel = [d for d in v.detalles if d.producto and d.producto.tipo_inventario == 'celulares']
        for d in detalles_cel:
            datos_historial.append({
                'id_venta': v.id,
                'fecha': v.fecha_venta,
                'vendedor': v.vendedor.nombre,
                'celular': f"{d.producto.nombre} (IMEI: {d.producto.imei or 'N/A'})",
                'precio_venta': d.precio_venta_final,
                'metodo_pago': v.metodo_pago_display
            })
            
    return render_template('celulares/historial_ventas.html', historial=datos_historial)



import pandas as pd
import io

@celulares_bp.route('/descargar_plantilla')
@login_required
@admin_required
def descargar_plantilla():
    # Definir las cabeceras exactas
    columnas = ['MARCA', 'REFERENCIA', 'CAPACIDAD', 'BATERIA', 'COLOR', 'IMEI 1', 'IMEI 2', 'PROVEEDOR', 'COSTO', 'P. MINIMO', 'P. SUGERIDO']
    df = pd.DataFrame(columns=columnas)
    
    # Crear un buffer en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Plantilla Celulares')
    
    output.seek(0)
    return send_file(output, download_name='plantilla_celulares.xlsx', as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@celulares_bp.route('/importar_excel', methods=['POST'])
@login_required
@admin_required
def importar_excel():
    if 'archivo_excel' not in request.files:
        flash('No se subió ningún archivo.', 'danger')
        return redirect(url_for('celulares_bp.inventario'))
        
    file = request.files['archivo_excel']
    if file.filename == '':
        flash('El archivo está vacío.', 'danger')
        return redirect(url_for('celulares_bp.inventario'))
        
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Formato de archivo no válido. Debe ser Excel (.xlsx o .xls).', 'danger')
        return redirect(url_for('celulares_bp.inventario'))
        
    try:
        df = pd.read_excel(file)
        # Limpiar nombres de columnas (quitar espacios extra y pasarlas a mayúsculas)
        df.columns = df.columns.str.strip().str.upper()
        
        columnas_esperadas = ['MARCA', 'REFERENCIA', 'CAPACIDAD', 'BATERIA', 'COLOR', 'IMEI 1', 'IMEI 2', 'PROVEEDOR', 'COSTO', 'P. MINIMO', 'P. SUGERIDO']
        
        for col in columnas_esperadas:
            if col not in df.columns:
                flash(f'El archivo no tiene la columna requerida: {col}', 'danger')
                return redirect(url_for('celulares_bp.inventario'))
                
        # Limpiar NaNs
        df = df.fillna('')
        
        exitosos = 0
        omitidos = 0
        
        for index, row in df.iterrows():
            imei1 = str(row['IMEI 1']).strip()
            # Si el IMEI está vacío, omitimos la fila
            if not imei1:
                continue
                
            # Limpiamos decimales en caso de que pandas haya leido el IMEI como float e.g. 123456.0
            if imei1.endswith('.0'):
                imei1 = imei1[:-2]
                
            # Verificar si existe el IMEI
            existente = Product.query.filter_by(imei=imei1, tipo_inventario='celulares').first()
            if existente:
                omitidos += 1
                continue
                
            marca = str(row['MARCA']).strip()
            referencia = str(row['REFERENCIA']).strip()
            memoria = str(row['CAPACIDAD']).strip()
            bateria_raw = str(row['BATERIA']).strip()
            bateria = bateria_raw
            if bateria_raw:
                if not bateria_raw.endswith('%'):
                    try:
                        val = float(bateria_raw)
                        if val <= 1.0 and val > 0:
                            bateria = f"{int(val * 100)}%"
                        else:
                            bateria = f"{int(val)}%"
                    except ValueError:
                        pass
            color = str(row['COLOR']).strip()
            
            imei2 = str(row['IMEI 2']).strip()
            if imei2.endswith('.0'):
                imei2 = imei2[:-2]
                
            proveedor = str(row['PROVEEDOR']).strip()
            
            # Limpiar precios (quitar $ y comas/puntos si vienen como texto)
            def clean_price(val):
                val = str(val).strip().replace('$', '').replace(',', '').replace(' ', '')
                try:
                    return float(val) if val else 0.0
                except:
                    return 0.0
                    
            costo = clean_price(row['COSTO'])
            minimo = clean_price(row['P. MINIMO'])
            sugerido = clean_price(row['P. SUGERIDO'])
            
            nombre_completo = f"Celular {marca} {referencia} {color} {memoria}".strip()
            sku_base = f"CEL-{datetime.now().strftime('%Y%m%d%H%M%S%f')}" # %f para evitar skus duplicados en el mismo segundo
            
            nuevo = Product(
                nombre=nombre_completo,
                sku=sku_base,
                tipo_inventario='celulares',
                cantidad_stock=1,
                precio_costo=costo,
                precio_minimo=minimo,
                precio_sugerido=sugerido,
                marca=marca,
                modelo_celular=referencia,
                color=color,
                bateria=bateria,
                memoria=memoria,
                imei=imei1,
                imei2=imei2,
                proveedor=proveedor
            )
            
            db.session.add(nuevo)
            exitosos += 1
            
        db.session.commit()
        
        mensaje = f'Carga Masiva completada: {exitosos} equipos subidos exitosamente.'
        if omitidos > 0:
            mensaje += f' Se omitieron {omitidos} equipos porque el IMEI 1 ya existía en el sistema.'
            
        flash(mensaje, 'success' if exitosos > 0 else 'warning')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error procesando el Excel: {str(e)}', 'danger')
        
    return redirect(url_for('celulares_bp.inventario'))

