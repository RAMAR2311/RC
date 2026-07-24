import os
from datetime import datetime
import pytz
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required
from models import db, Provider, ProviderInvoice, ProviderPayment
from decorators import admin_required

providers_bp = Blueprint('providers_bp', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@providers_bp.route('/')
@login_required
@admin_required
def list_providers():
    proveedores = Provider.query.order_by(Provider.nombre.asc()).all()
    return render_template('providers/list.html', proveedores=proveedores)

@providers_bp.route('/crear', methods=['POST'])
@login_required
@admin_required
def create_provider():
    nombre = request.form.get('nombre', '').strip()
    empresa = request.form.get('empresa', '').strip()
    telefono = request.form.get('telefono', '').strip()

    if not nombre:
        flash('El nombre del proveedor es obligatorio.', 'danger')
        return redirect(url_for('providers_bp.list_providers'))

    nuevo_proveedor = Provider(
        nombre=nombre,
        empresa=empresa,
        telefono=telefono
    )
    db.session.add(nuevo_proveedor)
    db.session.commit()
    
    flash('Proveedor registrado exitosamente.', 'success')
    return redirect(url_for('providers_bp.list_providers'))

@providers_bp.route('/<int:id>')
@login_required
@admin_required
def detail(id):
    proveedor = Provider.query.get_or_404(id)
    # The models use @property to calculate totals automatically.
    facturas = ProviderInvoice.query.filter_by(provider_id=id).order_by(ProviderInvoice.fecha_factura.desc()).all()
    pagos = ProviderPayment.query.filter_by(provider_id=id).order_by(ProviderPayment.fecha_pago.desc()).all()
    
    return render_template('providers/detail.html', 
                           proveedor=proveedor, 
                           facturas=facturas, 
                           pagos=pagos)

@providers_bp.route('/<int:id>/invoice', methods=['POST'])
@login_required
@admin_required
def add_invoice(id):
    proveedor = Provider.query.get_or_404(id)
    
    try:
        monto_total = float(request.form.get('monto_total', 0))
    except ValueError:
        monto_total = 0.0

    if monto_total <= 0:
        flash('El monto de la factura debe ser mayor a 0.', 'danger')
        return redirect(url_for('providers_bp.detail', id=id))

    numero_factura = request.form.get('numero_factura', '').strip()
    descripcion = request.form.get('descripcion', '').strip()
    
    filename = None
    if 'comprobante' in request.files:
        file = request.files['comprobante']
        if file and file.filename != '' and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            timestamp = datetime.now(pytz.timezone('America/Bogota')).strftime('%Y%m%d%H%M%S')
            filename = f"prov_{id}_{timestamp}.{ext}"
            
            # Ensure the directory exists
            upload_folder = os.path.join(current_app.static_folder, 'uploads', 'providers')
            os.makedirs(upload_folder, exist_ok=True)
            
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)

    nueva_factura = ProviderInvoice(
        provider_id=id,
        monto_total=monto_total,
        numero_factura=numero_factura,
        descripcion=descripcion,
        comprobante=filename
    )
    
    db.session.add(nueva_factura)
    db.session.commit()
    
    flash('Factura registrada correctamente.', 'success')
    return redirect(url_for('providers_bp.detail', id=id))

@providers_bp.route('/<int:id>/payment', methods=['POST'])
@login_required
@admin_required
def add_payment(id):
    proveedor = Provider.query.get_or_404(id)
    
    try:
        monto_abonado = float(request.form.get('monto_abonado', 0))
    except ValueError:
        monto_abonado = 0.0

    if monto_abonado <= 0:
        flash('El monto del abono debe ser mayor a 0.', 'danger')
        return redirect(url_for('providers_bp.detail', id=id))

    observacion = request.form.get('observacion', '').strip()
    
    nuevo_pago = ProviderPayment(
        provider_id=id,
        monto_abonado=monto_abonado,
        observacion=observacion
    )
    
    db.session.add(nuevo_pago)
    db.session.commit()
    
    flash('Abono registrado correctamente.', 'success')
    return redirect(url_for('providers_bp.detail', id=id))

@providers_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_provider(id):
    proveedor = Provider.query.get_or_404(id)
    
    # Delete physical files
    facturas = ProviderInvoice.query.filter_by(provider_id=id).all()
    upload_folder = os.path.join(current_app.static_folder, 'uploads', 'providers')
    for f in facturas:
        if f.comprobante:
            file_path = os.path.join(upload_folder, f.comprobante)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
    
    db.session.delete(proveedor)
    db.session.commit()
    
    flash('Proveedor eliminado correctamente.', 'success')
    return redirect(url_for('providers_bp.list_providers'))
