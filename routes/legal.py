import hashlib
from datetime import datetime
import pytz
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, ZenicDataAgreementAudit, obtener_hora_bogota
from decorators import admin_required

legal_bp = Blueprint('legal_bp', __name__, template_folder='../templates')

# DATOS OFICIALES E INMUTABLES DE ZENIC S.A.S. (EL ENCARGADO)
ZENIC_CORP_DATA = {
    'razon_social': 'ZENIC S.A.S.',
    'nit': '902067639-6',
    'representante_legal': 'Jhon Danny Gualdron Aparicio',
    'representante_id': '1004910859 de Bogotá',
    'domicilio': 'Bogotá D.C., Colombia',
    'version_acuerdo': 'v2026.1'
}

def obtener_ip_cliente():
    """Captura la IP pública real del cliente considerando proxies / balanceadores."""
    if request.headers.get('X-Forwarded-For'):
        # Puede venir una lista de IPs separada por comas (la primera es el cliente real)
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP').strip()
    else:
        ip = request.remote_addr or '127.0.0.1'
    return ip

@legal_bp.route('/acuerdo-datos')
@login_required
def ver_acuerdo():
    """Vista completa del Acuerdo DPA (con datos del comercio si ya está firmado o formulario de firma)."""
    acuerdo = ZenicDataAgreementAudit.query.order_by(ZenicDataAgreementAudit.id.desc()).first()
    return render_template('legal/acuerdo_datos.html', acuerdo=acuerdo, zenic=ZENIC_CORP_DATA)

@legal_bp.route('/contrato-anualidad')
@login_required
def ver_contrato_anualidad():
    """Vista completa e imprimible del Contrato de Licenciamiento y Custodia de Servidor en Modalidad Anualidad."""
    acuerdo = ZenicDataAgreementAudit.query.order_by(ZenicDataAgreementAudit.id.desc()).first()
    if not acuerdo:
        flash('Para generar y visualizar el Contrato de Anualidad y Licenciamiento, el Administrador debe diligenciar y firmar previamente el Protocolo de Tratamiento de Datos (DPA) con los datos legales de la empresa.', 'warning')
        return redirect(url_for('legal_bp.ver_acuerdo'))

    return render_template('legal/contrato_anualidad.html', acuerdo=acuerdo, zenic=ZENIC_CORP_DATA)

@legal_bp.route('/confirmar-pago-servidor/<token>', methods=['GET'])
@login_required
@admin_required
def confirmar_pago_servidor(token):
    """Endpoint con token criptográfico para registrar pago y extender corte de servidor."""
    from itsdangerous import URLSafeTimedSerializer
    from flask import current_app
    from models import ServerPayment, obtener_hora_bogota
    
    secret_key = current_app.config.get('SECRET_KEY', 'zenic_server_sec_2026')
    s = URLSafeTimedSerializer(secret_key)
    try:
        data = s.loads(token, salt='pago-servidor-zenic', max_age=86400 * 7) # Validez 7 días
        periodo = data.get('periodo')
        monto = data.get('monto', 180000.0)
        
        # Validar si ya existe pago registrado para el periodo
        existente = ServerPayment.query.filter_by(periodo_mes=periodo, estado='PAGADO').first()
        if not existente:
            nuevo_pago = ServerPayment(
                periodo_mes=periodo,
                monto=monto,
                referencia=f"CONF-TOKEN-{periodo}",
                metodo='Bre-B',
                estado='PAGADO',
                fecha_pago=obtener_hora_bogota(),
                registrado_por_id=current_user.id
            )
            db.session.add(nuevo_pago)
            db.session.commit()
            flash(f'¡Pago de servidor para el periodo {periodo} confirmado y certificado con éxito!', 'success')
        else:
            flash(f'El periodo {periodo} ya contaba con pago registrado.', 'info')
    except Exception as e:
        flash(f'El enlace o token de confirmación de pago no es válido o ha expirado: {str(e)}', 'danger')

    return redirect(url_for('admin_bp.dashboard') if hasattr(current_user, 'rol') and current_user.rol == 'admin' else url_for('index'))


@legal_bp.route('/firmar-acuerdo', methods=['POST'])
@login_required
@admin_required
def firmar_acuerdo():
    """Procesa y almacena la firma digital inmutable del DPA ante la SIC."""
    # Verificar si ya existe una firma vigente
    acuerdo_existente = ZenicDataAgreementAudit.query.filter_by(terms_version='v2026.1').first()
    if acuerdo_existente:
        flash('El Acuerdo de Transmisión de Datos ya fue firmado y certificado previamente.', 'info')
        return redirect(url_for('legal_bp.ver_acuerdo'))

    # Datos diligenciados por el comercio
    business_name = request.form.get('business_name', '').strip()
    business_nit = request.form.get('business_nit', '').strip()
    legal_rep = request.form.get('legal_representative', '').strip()
    legal_rep_id = request.form.get('legal_rep_id', '').strip()
    business_city = request.form.get('business_city', '').strip() or 'Bogotá D.C., Colombia'
    business_email = request.form.get('business_email', '').strip() or current_user.email
    signature_data = request.form.get('signature_data', '').strip()

    chk_terms = request.form.get('accepted_terms')
    chk_dpa = request.form.get('accepted_dpa')
    chk_media = request.form.get('accepted_media_release')

    # Validaciones Clickwrap estrictas
    if not chk_terms or not chk_dpa or not chk_media:
        flash('Es obligatorio marcar conscientemente todas las casillas de aceptación: términos, DPA y autorización de imagen.', 'danger')
        return redirect(request.referrer or url_for('legal_bp.ver_acuerdo'))

    if not business_name or not business_nit or not legal_rep or not legal_rep_id:
        flash('Todos los datos de identificación legal del comercio son obligatorios para la validez ante la SIC.', 'danger')
        return redirect(request.referrer or url_for('legal_bp.ver_acuerdo'))

    if not signature_data:
        flash('Debes estampar tu firma digital en el recuadro interactivo.', 'warning')
        return redirect(request.referrer or url_for('legal_bp.ver_acuerdo'))

    # Metadata probatoria (Ley 527 de 1999)
    ip_addr = obtener_ip_cliente()
    user_agent = request.headers.get('User-Agent', 'Desconocido')
    fecha_utc5 = obtener_hora_bogota()
    timestamp_iso = fecha_utc5.isoformat()

    # Generación de Hash Criptográfico SHA-256
    raw_payload = f"{business_nit}|{legal_rep_id}|{timestamp_iso}|{ZENIC_CORP_DATA['version_acuerdo']}|{ZENIC_CORP_DATA['nit']}"
    doc_hash = hashlib.sha256(raw_payload.encode('utf-8')).hexdigest()

    nuevo_acuerdo = ZenicDataAgreementAudit(
        client_id=1,
        user_id=current_user.id,
        business_name=business_name,
        business_nit=business_nit,
        legal_representative=legal_rep,
        legal_rep_id=legal_rep_id,
        business_city=business_city,
        business_email=business_email,
        accepted_terms=1,
        accepted_dpa=1,
        accepted_media_release=1,
        terms_version=ZENIC_CORP_DATA['version_acuerdo'],
        document_sha256=doc_hash,
        ip_address=ip_addr,
        user_agent=user_agent,
        signature_data=signature_data,
        timestamp_utc5=fecha_utc5
    )

    try:
        db.session.add(nuevo_acuerdo)
        db.session.commit()
        flash('¡Acuerdo de Transmisión de Datos firmado y registrado exitosamente ante la SIC!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al registrar la firma digital: {str(e)}', 'danger')

    return redirect(url_for('legal_bp.ver_acuerdo'))

@legal_bp.route('/estado-acuerdo', methods=['GET'])
@login_required
def estado_acuerdo():
    """Endpoint JSON para que el frontend o apps consulten el estado de firma."""
    acuerdo = ZenicDataAgreementAudit.query.filter_by(terms_version='v2026.1').first()
    if acuerdo:
        return jsonify({
            'firmado': True,
            'comercio': acuerdo.business_name,
            'representante': acuerdo.legal_representative,
            'fecha_firma': acuerdo.timestamp_utc5.strftime('%Y-%m-%d %H:%M:%S'),
            'sha256': acuerdo.document_sha256
        })
    return jsonify({'firmado': False})
