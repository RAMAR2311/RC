from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, send_file
from flask_login import login_required, current_user
from models import db, Product
from decorators import admin_required
from datetime import datetime
import pytz
import os
import pandas as pd
import io
from decimal import Decimal

externos_bp = Blueprint('externos_bp', __name__)

def obtener_hora_bogota():
    return datetime.now(pytz.timezone('America/Bogota')).replace(tzinfo=None)

@externos_bp.route('/')
@login_required
def inventario():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    base_query = Product.query.filter(
        Product.tipo_inventario == 'externos',
        ~Product.sku.like('EXTACC-%')
    )

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

    return render_template('externos/inventario.html',
                           celulares=paginacion.items,
                           paginacion=paginacion,
                           q=q)

@externos_bp.route('/accesorios')
@login_required
def inventario_accesorios():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    base_query = Product.query.filter(
        Product.tipo_inventario == 'externos',
        Product.sku.like('EXTACC-%')
    )

    if q:
        from sqlalchemy import or_
        base_query = base_query.filter(
            or_(
                Product.marca.ilike(f'%{q}%'),
                Product.nombre.ilike(f'%{q}%'),
                Product.proveedor.ilike(f'%{q}%'),
            )
        )

    paginacion = base_query.order_by(Product.fecha_creacion.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('externos/inventario_accesorios.html',
                           accesorios=paginacion.items,
                           paginacion=paginacion,
                           q=q)

@externos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo_externo():
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
        
        nombre_completo = f"Externo {marca} {modelo_celular} {color} {memoria}".strip()
        sku_base = f"EXT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        precio_sugerido = float(precio_sugerido_str) if precio_sugerido_str else 0.0

        nuevo = Product(
            nombre=nombre_completo,
            sku=sku_base,
            tipo_inventario='externos',
            cantidad_stock=1,
            precio_costo=float(precio_costo_str) if precio_costo_str else 0.0,
            precio_minimo=precio_sugerido, # El minimo toma el sugerido invisiblemente
            precio_sugerido=precio_sugerido,
            marca=marca,
            modelo_celular=modelo_celular,
            color=color,
            bateria=bateria,
            memoria=memoria,
            imei=imei,
            imei2=imei2,
            proveedor=proveedor
        )
        
        try:
            db.session.add(nuevo)
            db.session.commit()
            flash('Celular externo ingresado exitosamente.', 'success')
            return redirect(url_for('externos_bp.inventario'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar el celular externo: {str(e)}', 'danger')

    return render_template('externos/form_externo.html', celular=None)

@externos_bp.route('/api/nuevo_desde_caja', methods=['POST'])
@login_required
def api_nuevo_desde_caja():
    # AJAX endpoint for POS
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
    
    nombre_completo = f"Externo {marca} {modelo_celular} {color} {memoria}".strip()
    sku_base = f"EXT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    precio_sugerido = float(precio_sugerido_str) if precio_sugerido_str else 0.0

    nuevo = Product(
        nombre=nombre_completo,
        sku=sku_base,
        tipo_inventario='externos',
        cantidad_stock=1,
        precio_costo=float(precio_costo_str) if precio_costo_str else 0.0,
        precio_minimo=precio_sugerido,
        precio_sugerido=precio_sugerido,
        marca=marca,
        modelo_celular=modelo_celular,
        color=color,
        bateria=bateria,
        memoria=memoria,
        imei=imei,
        imei2=imei2,
        proveedor=proveedor
    )
    
    try:
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({
            'success': True,
            'product': {
                'id': nuevo.id,
                'sku': nuevo.sku,
                'nombre': nuevo.nombre,
                'precio_sugerido': float(nuevo.precio_sugerido),
                'precio_minimo': float(nuevo.precio_minimo),
                'stock': nuevo.cantidad_stock,
                'es_manual': False
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@externos_bp.route('/api_nuevo_accesorio_caja', methods=['POST'])
@login_required
def api_nuevo_accesorio_caja():
    # AJAX endpoint para accesorios externos desde caja
    nombre_accesorio = request.form.get('nombre_accesorio', '').strip()
    marca = request.form.get('marca', '').strip()
    proveedor = request.form.get('proveedor', '').strip()
    
    precio_costo_str = request.form.get('precio_costo', '0').replace(',', '')
    precio_sugerido_str = request.form.get('precio_sugerido', '0').replace(',', '')
    
    nombre_completo = f"Acc. Externo {marca} {nombre_accesorio}".strip()
    sku_base = f"EXTACC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    precio_sugerido = float(precio_sugerido_str) if precio_sugerido_str else 0.0

    nuevo = Product(
        nombre=nombre_completo,
        sku=sku_base,
        tipo_inventario='externos',
        cantidad_stock=1,
        precio_costo=float(precio_costo_str) if precio_costo_str else 0.0,
        precio_minimo=precio_sugerido,
        precio_sugerido=precio_sugerido,
        marca=marca,
        proveedor=proveedor
    )
    
    try:
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({
            'success': True,
            'product': {
                'id': nuevo.id,
                'sku': nuevo.sku,
                'nombre': nuevo.nombre,
                'precio_sugerido': float(nuevo.precio_sugerido),
                'precio_minimo': float(nuevo.precio_minimo),
                'stock': nuevo.cantidad_stock,
                'es_manual': False
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@externos_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_externo(id):
    celular = Product.query.get_or_404(id)
    if celular.tipo_inventario != 'externos':
        flash('El producto seleccionado no es un externo.', 'danger')
        return redirect(url_for('externos_bp.inventario'))
        
    if request.method == 'POST':
        celular.marca = request.form.get('marca', '').strip()
        celular.modelo_celular = request.form.get('modelo_celular', '').strip()
        celular.color = request.form.get('color', '').strip()
        celular.bateria = request.form.get('bateria', '').strip()
        celular.memoria = request.form.get('memoria', '').strip()
        celular.imei = request.form.get('imei', '').strip()
        celular.imei2 = request.form.get('imei2', '').strip()
        celular.proveedor = request.form.get('proveedor', '').strip()
        
        precio_costo_str = request.form.get('precio_costo', str(celular.precio_costo)).replace(',', '')
        precio_sugerido_str = request.form.get('precio_sugerido', str(celular.precio_sugerido)).replace(',', '')
        
        celular.precio_costo = float(precio_costo_str) if precio_costo_str else 0.0
        precio_sugerido = float(precio_sugerido_str) if precio_sugerido_str else 0.0
        celular.precio_sugerido = precio_sugerido
        celular.precio_minimo = precio_sugerido # Reflejado silenciosamente
        
        celular.nombre = f"Externo {celular.marca} {celular.modelo_celular} {celular.color} {celular.memoria}".strip()

        try:
            db.session.commit()
            flash('Celular externo actualizado correctamente.', 'success')
            return redirect(url_for('externos_bp.inventario'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar: {str(e)}', 'danger')
            
    return render_template('externos/form_externo.html', celular=celular)

@externos_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_externo(id):
    celular = Product.query.get_or_404(id)
    if celular.tipo_inventario != 'externos':
        flash('El producto seleccionado no es externo.', 'danger')
        return redirect(url_for('externos_bp.inventario'))
        
    try:
        db.session.delete(celular)
        db.session.commit()
        flash('Celular externo eliminado del sistema.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el celular: {str(e)}', 'danger')
        
    return redirect(url_for('externos_bp.inventario'))


@externos_bp.route('/enviar_inventario/<int:id>', methods=['POST'])
@login_required
@admin_required
def enviar_inventario(id):
    celular = Product.query.get_or_404(id)
    if celular.tipo_inventario != 'externos':
        flash('El producto seleccionado no es externo.', 'danger')
        return redirect(url_for('externos_bp.inventario'))
        
    try:
        # Clone the product for the main inventory
        nuevo_cel = Product(
            nombre=celular.nombre,
            sku=celular.sku + '-INV' if not celular.sku.endswith('-INV') else celular.sku,
            tipo_inventario='celulares',
            cantidad_stock=celular.cantidad_stock,
            precio_costo=celular.precio_costo,
            precio_minimo=celular.precio_minimo,
            precio_sugerido=celular.precio_sugerido,
            marca=celular.marca,
            modelo_celular=celular.modelo_celular,
            color=celular.color,
            bateria=celular.bateria,
            memoria=celular.memoria,
            imei=celular.imei,
            imei2=celular.imei2,
            proveedor=celular.proveedor
        )
        
        # Mark the original as sent and modify its IMEI to avoid unique constraint violations
        if celular.imei:
            celular.imei = celular.imei + '-EXT'
        celular.estado_celular = 'Enviado'
        celular.cantidad_stock = 0
        
        db.session.add(nuevo_cel)
        db.session.commit()
        flash('El producto ha sido enviado al Inventario de Celulares exitosamente, y se ha guardado el registro.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al mover el producto: {str(e)}', 'danger')
        
    return redirect(url_for('externos_bp.inventario'))


@externos_bp.route('/descargar_plantilla')
@login_required
@admin_required
def descargar_plantilla():
    columnas = ['MARCA', 'REFERENCIA', 'CAPACIDAD', 'BATERIA', 'COLOR', 'IMEI', 'IMEI2', 'PROVEEDOR', 'COSTO', 'PRECIO SUGERIDO']
    df = pd.DataFrame(columns=columnas)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Plantilla Externos')
    
    output.seek(0)
    return send_file(output, download_name='plantilla_externos.xlsx', as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@externos_bp.route('/importar_excel', methods=['POST'])
@login_required
@admin_required
def importar_excel():
    if 'archivo_excel' not in request.files:
        flash('No se subió ningún archivo.', 'danger')
        return redirect(url_for('externos_bp.inventario'))
        
    file = request.files['archivo_excel']
    if file.filename == '':
        flash('El archivo está vacío.', 'danger')
        return redirect(url_for('externos_bp.inventario'))
        
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Formato de archivo no válido. Debe ser Excel (.xlsx o .xls).', 'danger')
        return redirect(url_for('externos_bp.inventario'))
        
    try:
        df = pd.read_excel(file)
        df.columns = df.columns.str.strip().str.upper()
        
        columnas_esperadas = ['MARCA', 'REFERENCIA', 'CAPACIDAD', 'BATERIA', 'COLOR', 'IMEI', 'IMEI2', 'PROVEEDOR', 'COSTO', 'PRECIO SUGERIDO']
        
        for col in columnas_esperadas:
            if col not in df.columns:
                flash(f'El archivo no tiene la columna requerida: {col}', 'danger')
                return redirect(url_for('externos_bp.inventario'))
                
        df = df.fillna('')
        
        exitosos = 0
        omitidos = 0
        
        for index, row in df.iterrows():
            imei1 = str(row['IMEI']).strip()
            if not imei1:
                continue
                
            if imei1.endswith('.0'):
                imei1 = imei1[:-2]
                
            existente = Product.query.filter_by(imei=imei1).first()
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
            
            imei2 = str(row['IMEI2']).strip()
            if imei2.endswith('.0'):
                imei2 = imei2[:-2]
                
            proveedor = str(row['PROVEEDOR']).strip()
            
            # Limpiar precios de simbolos $ o comas
            def limpiar_precio(val):
                s = str(val).replace('$', '').replace(',', '').strip()
                try:
                    return float(s) if s else 0.0
                except:
                    return 0.0

            costo = limpiar_precio(row['COSTO'])
            sugerido = limpiar_precio(row['PRECIO SUGERIDO'])
            
            nombre_completo = f"Externo {marca} {referencia} {color} {memoria}".strip()
            sku_base = f"EXT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{index}"
            
            nuevo_cel = Product(
                nombre=nombre_completo,
                sku=sku_base,
                tipo_inventario='externos',
                cantidad_stock=1,
                precio_costo=costo,
                precio_minimo=sugerido,
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
            
            db.session.add(nuevo_cel)
            exitosos += 1
            
        db.session.commit()
        
        if omitidos > 0:
            flash(f'Carga completada: {exitosos} externos subidos. Se omitieron {omitidos} porque el IMEI ya existía en el sistema.', 'warning')
        else:
            flash(f'Carga Masiva completada: {exitosos} externos subidos exitosamente.', 'success')
            
        return redirect(url_for('externos_bp.inventario'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al procesar el archivo: {str(e)}', 'danger')
        return redirect(url_for('externos_bp.inventario'))
