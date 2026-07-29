import os
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect

# Importar la instancia de db desde models
from models import db, User

def create_app():
    app = Flask(__name__)
    
    # Configuración mediante variables de entorno (con fallback inteligente a SQLite si Postgres no está activo)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-super-secreta')
    
    raw_db_url = os.environ.get('DATABASE_URL', 'postgresql://postgres:admin123@localhost:5432/RC')
    
    # Verificar si PostgreSQL está disponible
    if raw_db_url and raw_db_url.startswith('postgresql'):
        try:
            from sqlalchemy import create_engine
            engine = create_engine(raw_db_url, connect_args={'connect_timeout': 2})
            with engine.connect() as conn:
                pass
            app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url
        except Exception:
            instance_db = os.path.join(app.instance_path, 'crm_inventory.db')
            root_db = os.path.join(app.root_path, 'crm_inventory.db')
            if os.path.exists(instance_db):
                app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{instance_db}'
            elif os.path.exists(root_db):
                app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{root_db}'
            else:
                app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{instance_db}'
            print(f"⚠️ [INFO] PostgreSQL no disponible localmente. Usando SQLite: {app.config['SQLALCHEMY_DATABASE_URI']}")
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')

    # Inicializar Extensiones
    db.init_app(app)
    Migrate(app, db)
    CSRFProtect(app)
    
    login_manager = LoginManager()
    login_manager.login_view = 'auth_bp.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Importar y Registrar Blueprints
    from routes.sales import sales_bp
    from routes.inventory import inventory_bp
    from routes.auth import auth_bp
    from routes.arqueo import arqueo_bp
    from routes.gastos import gastos_bp
    
    app.register_blueprint(sales_bp, url_prefix='/sales')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(arqueo_bp, url_prefix='/arqueo')
    app.register_blueprint(gastos_bp, url_prefix='/gastos')
    
    # Registro de Blueprint Admin
    from routes.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Registro de Blueprint Bodega
    from routes.bodega import bodega_bp
    app.register_blueprint(bodega_bp, url_prefix='/bodega')

    # Registro de Blueprint Celulares
    from routes.celulares import celulares_bp
    app.register_blueprint(celulares_bp, url_prefix='/celulares')

    # Registro de Blueprint Externos
    from routes.externos import externos_bp
    app.register_blueprint(externos_bp, url_prefix='/externos')

    # Registro de Blueprint Retomas
    from routes.retomas import retomas_bp
    app.register_blueprint(retomas_bp, url_prefix='/retomas')

    # Registro de Blueprint Proveedores
    from routes.providers import providers_bp
    app.register_blueprint(providers_bp, url_prefix='/proveedores')

    # Registro de Blueprint Garantías
    from routes.warranties import warranties_bp
    app.register_blueprint(warranties_bp, url_prefix='/garantias')

    # Registro de Blueprint Aprobaciones
    from routes.approvals import approvals_bp
    app.register_blueprint(approvals_bp)


    @app.template_filter('cop')
    def cop_filter(value):
        if value is None:
            return "0"
        try:
            # Formateo a moneda colombiana (separador de miles con coma, como pidió el usuario)
            return "{:,.0f}".format(float(value))
        except (ValueError, TypeError):
            return value

    @app.route('/')
    def index():
        # Redirección de sesión y rol de usuario
        if not current_user.is_authenticated:
            return redirect(url_for('auth_bp.login'))
            
        if current_user.rol == 'admin':
            return redirect(url_for('admin_bp.dashboard'))
            
        if current_user.rol == 'bodega' or current_user.rol == 'vendedor_bodega':
            return redirect(url_for('bodega_bp.dashboard'))
            
        # Por defecto, Vendedores van directo a Caja Visual
        return redirect(url_for('sales_bp.caja_visual'))

    @app.route('/sw.js')
    def service_worker():
        from flask import send_from_directory
        return send_from_directory('static', 'sw.js', mimetype='application/javascript')

    return app

if __name__ == '__main__':
    app = create_app()
    
    # ---------------- LÓGICA DE INICIALIZACIÓN ----------------
    with app.app_context():
        from models import db, User
        from werkzeug.security import generate_password_hash
        
        # Aseguramos que las tablas existan sin romper migraciones
        db.create_all()
        
        # Crear la carpeta de imágenes si no existe
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Verificamos e instanciamos al Administrador si no existe
        if not User.query.filter_by(email='admin@redcover.com').first():
            master_admin = User(
                nombre='Administrador Principal',
                email='admin@redcover.com',
                password_hash=generate_password_hash('Admin123'),
                rol='admin' # Rol dictaminado por los requerimientos
            )
            db.session.add(master_admin)
            db.session.commit()
            print("🚀 [INFO] Usuario maestro 'admin@redcover.com' fue creado automáticamente.")
            
    port = int(os.environ.get('PORT', 5001))
    print(f"\n🌐 Servidor iniciado correctamente.")
    print(f"👉 Abre tu navegador en Mac (Chrome/Safari): http://localhost:{port} o http://127.0.0.1:{port}\n")
    app.run(host='0.0.0.0', port=port, debug=True)
