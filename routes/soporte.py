from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from decimal import Decimal
from datetime import datetime
from decorators import admin_required
from models import (
    db, Product, Retoma, Warranty, Tecnico, SoporteTecnico, Asesor,
    StockAdjustment, obtener_hora_bogota
)

soporte_bp = Blueprint('soporte_bp', __name__)


def _acceso_soporte():
    return current_user.rol in ['admin', 'vendedor']


@soporte_bp.route('/', methods=['GET'])
@login_required
def index():
    if not _acceso_soporte():
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('index'))

    en_soporte = SoporteTecnico.query.filter(
        SoporteTecnico.estado.in_(['EN_SOPORTE', 'EN_REPARACION', 'LISTO', 'NO_REPARABLE'])
    ).order_by(SoporteTecnico.fecha_ingreso.desc()).all()

    historial = SoporteTecnico.query.filter_by(estado='DEVUELTO').order_by(
        SoporteTecnico.fecha_salida.desc()
    ).limit(100).all()

    tecnicos = Tecnico.query.order_by(Tecnico.nombre.asc()).all()
    tecnicos_activos = [t for t in tecnicos if t.activo]
    asesores_activos = Asesor.query.filter_by(activo=True).order_by(Asesor.nombre.asc()).all()

    return render_template(
        'soporte/index.html',
        en_soporte=en_soporte,
        historial=historial,
        tecnicos=tecnicos,
        tecnicos_activos=tecnicos_activos,
        asesores_activos=asesores_activos
    )


@soporte_bp.route('/api/tecnicos', methods=['GET'])
@login_required
def api_tecnicos():
    tecnicos = Tecnico.query.filter_by(activo=True).order_by(Tecnico.nombre.asc()).all()
    asesores = Asesor.query.filter_by(activo=True).order_by(Asesor.nombre.asc()).all()
    return jsonify({
        'success': True,
        'tecnicos': [
            {
                'id': t.id,
                'nombre': t.nombre,
                'telefono': t.telefono or '',
                'especialidad': t.especialidad or ''
            }
            for t in tecnicos
        ],
        'asesores': [
            {
                'id': a.id,
                'nombre': a.nombre
            }
            for a in asesores
        ]
    })


@soporte_bp.route('/tecnicos/nuevo', methods=['POST'])
@login_required
@admin_required
def nuevo_tecnico():
    nombre = request.form.get('nombre', '').strip()
    telefono = request.form.get('telefono', '').strip() or None
    especialidad = request.form.get('especialidad', '').strip() or None

    if not nombre:
        flash('El nombre del técnico es obligatorio.', 'danger')
        return redirect(url_for('soporte_bp.index'))

    try:
        t = Tecnico(nombre=nombre, telefono=telefono, especialidad=especialidad, activo=True)
        db.session.add(t)
        db.session.commit()
        flash(f'Técnico "{nombre}" registrado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al registrar el técnico: {str(e)}', 'danger')

    return redirect(url_for('soporte_bp.index'))


@soporte_bp.route('/tecnicos/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_tecnico(id):
    tecnico = Tecnico.query.get_or_404(id)
    try:
        SoporteTecnico.query.filter_by(tecnico_id=tecnico.id).update({'tecnico_id': None})
        db.session.delete(tecnico)
        db.session.commit()
        flash(f'Técnico "{tecnico.nombre}" eliminado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar técnico: {str(e)}', 'danger')

    return redirect(url_for('soporte_bp.index'))


@soporte_bp.route('/enviar', methods=['POST'])
@login_required
def enviar_soporte():
    if not _acceso_soporte():
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('index'))

    origen = request.form.get('origen', 'inventario').strip().lower()
    ids_raw = request.form.getlist('item_ids')
    if not ids_raw and request.form.get('item_ids_str'):
        ids_raw = [x.strip() for x in request.form.get('item_ids_str').split(',') if x.strip()]

    tecnico_id_str = request.form.get('tecnico_id', '').strip()
    tecnico_manual = request.form.get('tecnico_manual', '').strip()
    asesor_id_str = request.form.get('asesor_id', '').strip()
    tipo_arreglo = request.form.get('tipo_arreglo', 'Diagnóstico General / Revisión').strip()
    fecha_entrega_str = request.form.get('fecha_entrega_estimada', '').strip()
    falla_reportada = request.form.get('falla_reportada', '').strip()
    costo_raw = request.form.get('costo_reparacion', '0').replace(',', '').replace('.', '').strip()

    try:
        costo_val = Decimal(costo_raw) if costo_raw else Decimal('0')
        if costo_val < 0:
            costo_val = Decimal('0')
    except Exception:
        costo_val = Decimal('0')

    fecha_entrega_val = None
    if fecha_entrega_str:
        try:
            fecha_entrega_val = datetime.strptime(fecha_entrega_str, '%Y-%m-%d').date()
        except Exception:
            fecha_entrega_val = None

    asesor_obj = None
    asesor_nombre = None
    if asesor_id_str and asesor_id_str.isdigit():
        asesor_obj = Asesor.query.get(int(asesor_id_str))
        if asesor_obj:
            asesor_nombre = asesor_obj.nombre

    if not ids_raw:
        flash('Debes seleccionar al menos un equipo para enviar a soporte técnico.', 'warning')
        return redirect(request.referrer or url_for('soporte_bp.index'))

    if not falla_reportada:
        flash('Debes indicar el detalle o trabajo a realizar en soporte técnico.', 'danger')
        return redirect(request.referrer or url_for('soporte_bp.index'))

    tecnico_obj = None
    tecnico_nombre = ''

    if tecnico_id_str and tecnico_id_str != '__OTRO__' and tecnico_id_str.isdigit():
        tecnico_obj = Tecnico.query.get(int(tecnico_id_str))
        if tecnico_obj:
            tecnico_nombre = tecnico_obj.nombre

    if not tecnico_nombre and tecnico_manual:
        tecnico_nombre = tecnico_manual
        tecnico_obj = Tecnico.query.filter(Tecnico.nombre.ilike(tecnico_manual)).first()
        if not tecnico_obj:
            tecnico_obj = Tecnico(nombre=tecnico_manual, activo=True)
            db.session.add(tecnico_obj)
            db.session.flush()

    if not tecnico_nombre:
        flash('Debes seleccionar o escribir el técnico encargado.', 'danger')
        return redirect(request.referrer or url_for('soporte_bp.index'))

    try:
        ids = [int(i) for i in ids_raw]
    except ValueError:
        flash('Identificadores inválidos.', 'danger')
        return redirect(request.referrer or url_for('soporte_bp.index'))

    creados = 0
    omitidos = 0

    try:
        if origen == 'inventario':
            productos = Product.query.with_for_update().filter(
                Product.id.in_(ids),
                Product.tipo_inventario == 'celulares'
            ).all()
            for p in productos:
                if p.cantidad_stock < 1 or p.maneo_activo or p.soporte_activo:
                    omitidos += 1
                    continue
                stock_anterior = p.cantidad_stock
                p.cantidad_stock -= 1

                orden = SoporteTecnico(
                    origen='inventario',
                    product_id=p.id,
                    tecnico_id=tecnico_obj.id if tecnico_obj else None,
                    tecnico_nombre=tecnico_nombre,
                    asesor_id=asesor_obj.id if asesor_obj else None,
                    asesor_nombre=asesor_nombre,
                    tipo_arreglo=tipo_arreglo,
                    fecha_entrega_estimada=fecha_entrega_val,
                    equipo_nombre=p.nombre,
                    imei=p.imei or p.sku,
                    falla_reportada=falla_reportada,
                    costo_reparacion=costo_val,
                    estado='EN_SOPORTE',
                    usuario_id=current_user.id
                )
                db.session.add(orden)
                db.session.flush()

                ajuste = StockAdjustment(
                    product_id=p.id,
                    admin_id=current_user.id,
                    tipo_movimiento=f"Envío a Soporte Técnico #{orden.id} ({tecnico_nombre})",
                    stock_anterior=stock_anterior,
                    stock_nuevo=p.cantidad_stock
                )
                db.session.add(ajuste)
                creados += 1

        elif origen == 'retoma':
            retomas = Retoma.query.filter(Retoma.id.in_(ids)).all()
            for r in retomas:
                ya_activo = SoporteTecnico.query.filter(
                    SoporteTecnico.retoma_id == r.id,
                    SoporteTecnico.estado.in_(['EN_SOPORTE', 'LISTO'])
                ).first()
                if ya_activo:
                    omitidos += 1
                    continue

                if r.producto_generado and r.producto_generado.cantidad_stock > 0:
                    prod_gen = Product.query.with_for_update().get(r.producto_generado.id)
                    if prod_gen and prod_gen.cantidad_stock > 0:
                        stock_ant = prod_gen.cantidad_stock
                        prod_gen.cantidad_stock -= 1
                        db.session.add(StockAdjustment(
                            product_id=prod_gen.id,
                            admin_id=current_user.id,
                            tipo_movimiento=f"Envío a Soporte Técnico desde Retoma #{r.id} ({tecnico_nombre})",
                            stock_anterior=stock_ant,
                            stock_nuevo=prod_gen.cantidad_stock
                        ))

                nombre_eq = f"{r.marca or ''} {r.modelo} {r.memoria or ''} {r.color or ''}".strip()
                orden = SoporteTecnico(
                    origen='retoma',
                    retoma_id=r.id,
                    product_id=r.producto_generado_id,
                    tecnico_id=tecnico_obj.id if tecnico_obj else None,
                    tecnico_nombre=tecnico_nombre,
                    asesor_id=asesor_obj.id if asesor_obj else None,
                    asesor_nombre=asesor_nombre,
                    tipo_arreglo=tipo_arreglo,
                    fecha_entrega_estimada=fecha_entrega_val,
                    equipo_nombre=nombre_eq,
                    imei=r.imei1,
                    falla_reportada=falla_reportada,
                    costo_reparacion=costo_val,
                    estado='EN_SOPORTE',
                    usuario_id=current_user.id
                )
                db.session.add(orden)
                creados += 1

        elif origen == 'garantia':
            garantias = Warranty.query.filter(Warranty.id.in_(ids)).all()
            for w in garantias:
                ya_activo = SoporteTecnico.query.filter(
                    SoporteTecnico.warranty_id == w.id,
                    SoporteTecnico.estado.in_(['EN_SOPORTE', 'LISTO'])
                ).first()
                if ya_activo:
                    omitidos += 1
                    continue

                nombre_eq = w.product.nombre if w.product else (w.nombre_manual or f'Garantía #{w.id}')
                imei_eq = w.product.imei if w.product and w.product.imei else None

                orden = SoporteTecnico(
                    origen='garantia',
                    warranty_id=w.id,
                    product_id=w.product_id,
                    tecnico_id=tecnico_obj.id if tecnico_obj else None,
                    tecnico_nombre=tecnico_nombre,
                    asesor_id=asesor_obj.id if asesor_obj else None,
                    asesor_nombre=asesor_nombre,
                    tipo_arreglo=tipo_arreglo,
                    fecha_entrega_estimada=fecha_entrega_val,
                    equipo_nombre=nombre_eq,
                    imei=imei_eq,
                    falla_reportada=falla_reportada,
                    costo_reparacion=costo_val,
                    estado='EN_SOPORTE',
                    usuario_id=current_user.id
                )
                db.session.add(orden)
                db.session.flush()

                nota = f"En Soporte Técnico #{orden.id} ({tecnico_nombre})"
                w.admin_notes = f"{w.admin_notes} | {nota}" if w.admin_notes else nota
                creados += 1

        db.session.commit()
        if creados > 0:
            msg = f'Se enviaron {creados} equipo(s) a Soporte Técnico (Técnico: {tecnico_nombre}).'
            if omitidos > 0:
                msg += f' ({omitidos} omitido(s) por no estar disponibles o ya estar en soporte.)'
            flash(msg, 'success')
        else:
            flash('No se pudo enviar ningún equipo (ya estaban en soporte o sin stock activo).', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al enviar a soporte técnico: {str(e)}', 'danger')

    return redirect(url_for('soporte_bp.index'))


def _finalizar_y_devolver_orden(orden, sumar_al_costo=True):
    """Marca la orden como DEVUELTO (Historial) y envía siempre el equipo al Inventario de Celulares."""
    costo_val = Decimal(str(orden.costo_reparacion or 0))
    orden.estado = 'DEVUELTO'
    orden.fecha_salida = obtener_hora_bogota()
    orden.resuelto_por_id = current_user.id

    if orden.origen == 'inventario' and orden.product_id:
        prod = Product.query.with_for_update().get(orden.product_id)
        if prod and prod.cantidad_stock == 0 and not prod.maneo_activo:
            stock_ant = prod.cantidad_stock
            prod.cantidad_stock = 1
            if sumar_al_costo and costo_val > 0:
                prod.precio_costo = Decimal(str(prod.precio_costo or 0)) + costo_val
            db.session.add(StockAdjustment(
                product_id=prod.id,
                admin_id=current_user.id,
                tipo_movimiento=f"Ingreso desde Soporte Técnico #{orden.id}",
                stock_anterior=stock_ant,
                stock_nuevo=1
            ))

    elif orden.origen == 'retoma' and orden.retoma_id:
        ret = Retoma.query.get(orden.retoma_id)
        if ret:
            if sumar_al_costo and costo_val > 0:
                ret.arreglos = Decimal(str(ret.arreglos or 0)) + costo_val
            if ret.producto_generado_id:
                prod = Product.query.with_for_update().get(ret.producto_generado_id)
                if prod and prod.cantidad_stock == 0 and not prod.maneo_activo:
                    stock_ant = prod.cantidad_stock
                    prod.cantidad_stock = 1
                    if sumar_al_costo and costo_val > 0:
                        prod.precio_costo = Decimal(str(prod.precio_costo or 0)) + costo_val
                    db.session.add(StockAdjustment(
                        product_id=prod.id,
                        admin_id=current_user.id,
                        tipo_movimiento=f"Ingreso a Inventario desde Soporte Técnico #{orden.id} (Retoma #{ret.id})",
                        stock_anterior=stock_ant,
                        stock_nuevo=1
                    ))
            else:
                imei1_val = ret.imei1.strip() if ret.imei1 else None
                if imei1_val:
                    prod_existente = Product.query.filter_by(imei=imei1_val).first()
                    if prod_existente and prod_existente.cantidad_stock == 0:
                        prod_existente.imei = f"{imei1_val}-OLD-{prod_existente.id}"
                        db.session.flush()
                costo_total_ret = Decimal(str(ret.valor_retoma or 0)) + Decimal(str(ret.arreglos or 0))
                nombre_def = f"{ret.marca or ''} {ret.modelo} {ret.color or ''} {ret.memoria or ''}".strip()
                nuevo_prod = Product(
                    nombre=nombre_def,
                    sku=f"RET-{ret.id}-{obtener_hora_bogota().strftime('%Y%m%d%H%M%S')}",
                    tipo_inventario='celulares',
                    inventario=getattr(current_user, 'sucursal', None) or 'LOCAL 136',
                    cantidad_stock=1,
                    precio_costo=costo_total_ret,
                    precio_minimo=costo_total_ret,
                    precio_sugerido=costo_total_ret + Decimal('50000'),
                    observacion=ret.observaciones,
                    imei=imei1_val,
                    imei2=ret.imei2.strip() if ret.imei2 else None,
                    color=ret.color,
                    bateria=ret.bateria,
                    memoria=ret.memoria,
                    proveedor=ret.proveedor or 'Cliente',
                    marca=ret.marca or '',
                    modelo_celular=ret.modelo,
                    estado_celular='Usado'
                )
                db.session.add(nuevo_prod)
                db.session.flush()
                ret.producto_generado_id = nuevo_prod.id
                ret.estado = 'aprobado'
                orden.product_id = nuevo_prod.id
                db.session.add(StockAdjustment(
                    product_id=nuevo_prod.id,
                    admin_id=current_user.id,
                    tipo_movimiento=f"Ingreso a Inventario desde Soporte Técnico #{orden.id} (Retoma #{ret.id})",
                    stock_anterior=0,
                    stock_nuevo=1
                ))

    elif orden.origen == 'garantia' and orden.warranty_id:
        w = Warranty.query.get(orden.warranty_id)
        if w and w.product_id:
            prod = Product.query.with_for_update().get(w.product_id)
            if prod and prod.cantidad_stock == 0 and not prod.maneo_activo:
                stock_ant = prod.cantidad_stock
                prod.cantidad_stock = 1
                if sumar_al_costo and costo_val > 0:
                    prod.precio_costo = Decimal(str(prod.precio_costo or 0)) + costo_val
                db.session.add(StockAdjustment(
                    product_id=prod.id,
                    admin_id=current_user.id,
                    tipo_movimiento=f"Ingreso a Inventario desde Soporte Técnico #{orden.id} (Garantía #{w.id})",
                    stock_anterior=stock_ant,
                    stock_nuevo=1
                ))
            w.devuelto_inventario = True
            resumen = f"Reparado en Soporte #{orden.id} y enviado a Inventario"
            detalle_rep = orden.trabajo_realizado or orden.diagnostico
            if detalle_rep:
                resumen += f": {detalle_rep}"
            w.admin_notes = f"{w.admin_notes} | {resumen}" if w.admin_notes else resumen
        else:
            nuevo_prod = Product(
                nombre=orden.equipo_nombre,
                sku=f"SOP-{orden.id}-{obtener_hora_bogota().strftime('%Y%m%d%H%M%S')}",
                tipo_inventario='celulares',
                inventario=getattr(current_user, 'sucursal', None) or 'LOCAL 136',
                cantidad_stock=1,
                precio_costo=costo_val,
                precio_minimo=costo_val,
                precio_sugerido=costo_val,
                imei=orden.imei
            )
            db.session.add(nuevo_prod)
            db.session.flush()
            orden.product_id = nuevo_prod.id
            db.session.add(StockAdjustment(
                product_id=nuevo_prod.id,
                admin_id=current_user.id,
                tipo_movimiento=f"Ingreso a Inventario desde Soporte Técnico #{orden.id}",
                stock_anterior=0,
                stock_nuevo=1
            ))


@soporte_bp.route('/actualizar/<int:id>', methods=['POST'])
@login_required
def actualizar_soporte(id):
    if not _acceso_soporte():
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('index'))

    orden = SoporteTecnico.query.get_or_404(id)
    estado = request.form.get('estado', orden.estado).strip()
    tecnico_id_str = request.form.get('tecnico_id', '').strip()
    asesor_id_str = request.form.get('asesor_id', '').strip()
    diagnostico = request.form.get('diagnostico', '').strip() or None
    trabajo_realizado = request.form.get('trabajo_realizado', '').strip() or None
    costo_raw = request.form.get('costo_reparacion', '0').replace(',', '').replace('.', '').strip()
    sumar_al_costo = request.form.get('sumar_al_costo') == 'on'

    try:
        costo_val = Decimal(costo_raw) if costo_raw else Decimal('0')
        if costo_val < 0:
            costo_val = Decimal('0')
    except Exception:
        costo_val = Decimal('0')

    try:
        if tecnico_id_str.isdigit():
            t = Tecnico.query.get(int(tecnico_id_str))
            if t:
                orden.tecnico_id = t.id
                orden.tecnico_nombre = t.nombre
        if asesor_id_str.isdigit():
            a = Asesor.query.get(int(asesor_id_str))
            if a:
                orden.asesor_id = a.id
                orden.asesor_nombre = a.nombre
        orden.diagnostico = diagnostico
        orden.trabajo_realizado = trabajo_realizado
        orden.costo_reparacion = costo_val

        if estado == 'LISTO':
            _finalizar_y_devolver_orden(orden, sumar_al_costo=sumar_al_costo)
            db.session.commit()
            flash(f'Servicio técnico #{orden.id} marcado como Listo / Entregado y enviado al Inventario.', 'success')
        else:
            if estado in ('EN_SOPORTE', 'EN_REPARACION', 'NO_REPARABLE'):
                orden.estado = estado
            db.session.commit()
            flash(f'Servicio técnico #{orden.id} actualizado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar orden: {str(e)}', 'danger')

    return redirect(url_for('soporte_bp.index'))


@soporte_bp.route('/devolver/<int:id>', methods=['POST'])
@login_required
def devolver_soporte(id):
    if not _acceso_soporte():
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('index'))

    orden = SoporteTecnico.query.get_or_404(id)
    if orden.estado == 'DEVUELTO':
        flash('Esta orden ya fue finalizada y devuelta.', 'warning')
        return redirect(url_for('soporte_bp.index'))

    trabajo_realizado = request.form.get('trabajo_realizado', orden.trabajo_realizado or '').strip() or None
    costo_raw = request.form.get('costo_reparacion', str(int(orden.costo_reparacion or 0))).replace(',', '').replace('.', '').strip()
    sumar_al_costo = request.form.get('sumar_al_costo') == 'on'

    try:
        costo_val = Decimal(costo_raw) if costo_raw else Decimal('0')
        if costo_val < 0:
            costo_val = Decimal('0')
    except Exception:
        costo_val = Decimal('0')

    try:
        orden.trabajo_realizado = trabajo_realizado
        orden.costo_reparacion = costo_val
        _finalizar_y_devolver_orden(orden, sumar_al_costo=sumar_al_costo)
        db.session.commit()
        flash(f'Orden #{orden.id} finalizada y equipo devuelto a {orden.origen}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al devolver el equipo: {str(e)}', 'danger')

    return redirect(url_for('soporte_bp.index'))


@soporte_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_soporte(id):
    orden = SoporteTecnico.query.get_or_404(id)
    try:
        if orden.estado != 'DEVUELTO' and orden.origen == 'inventario' and orden.product_id:
            prod = Product.query.with_for_update().get(orden.product_id)
            if prod and prod.cantidad_stock == 0 and not prod.maneo_activo:
                prod.cantidad_stock = 1
                db.session.add(StockAdjustment(
                    product_id=prod.id,
                    admin_id=current_user.id,
                    tipo_movimiento=f"Anulación Soporte Técnico #{orden.id}",
                    stock_anterior=0,
                    stock_nuevo=1
                ))
        db.session.delete(orden)
        db.session.commit()
        flash(f'Orden de soporte #{id} eliminada.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar orden de soporte: {str(e)}', 'danger')

    return redirect(url_for('soporte_bp.index'))
