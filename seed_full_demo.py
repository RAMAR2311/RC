import os
import sys
from decimal import Decimal
from datetime import datetime, timedelta, date
from app import create_app
from models import (
    db, User, Product, ProductVariant, Sale, SaleDetail, SalePayment,
    SaleClient, Asesor, Provider, ProviderInvoice, ProviderPayment,
    ArqueoCaja, SobranteLog, Maneo, Expense, Cliente, FacturaBodega,
    FacturaBodegaDetalle, AbonoBodega, Warranty, PriceApproval,
    StockAdjustment, Retoma, obtener_hora_bogota
)
from werkzeug.security import generate_password_hash

def seed_all():
    app = create_app()
    with app.app_context():
        print("==================================================")
        print("[*] INICIANDO SEMBRADO COMPLETO DE DATOS DE DEMO")
        print("==================================================")

        # 0. Asegurar tablas y directorios
        db.create_all()
        os.makedirs(os.path.join(app.root_path, 'static', 'uploads'), exist_ok=True)
        os.makedirs(os.path.join(app.root_path, 'static', 'uploads', 'facturas'), exist_ok=True)
        now = obtener_hora_bogota()

        # ----------------------------------------------------
        # 1. USUARIOS Y ROLES
        # ----------------------------------------------------
        print("\n[1/13] Configurando Usuarios y Roles...")
        users_data = [
            {
                "email": "admin@redcover.com",
                "nombre": "Administrador Principal",
                "telefono": "3001234567",
                "rol": "admin",
                "sucursal": "LOCAL 136",
                "pass": "Admin123"
            },
            {
                "email": "vendedor@redcover.com",
                "nombre": "Cajero Local 197",
                "telefono": "3007654321",
                "rol": "vendedor",
                "sucursal": "LOCAL 197",
                "pass": "ventas123"
            },
            {
                "email": "vendedor136@redcover.com",
                "nombre": "Cajero Local 136",
                "telefono": "3119876543",
                "rol": "vendedor",
                "sucursal": "LOCAL 136",
                "pass": "ventas123"
            },
            {
                "email": "bodega@redcover.com",
                "nombre": "Encargado de Bodega Central",
                "telefono": "3154567890",
                "rol": "bodega",
                "sucursal": "BODEGA PRINCIPAL",
                "pass": "bodega123"
            }
        ]

        users = {}
        for u in users_data:
            user_obj = User.query.filter_by(email=u["email"]).first()
            if not user_obj:
                user_obj = User(
                    nombre=u["nombre"],
                    email=u["email"],
                    telefono=u["telefono"],
                    rol=u["rol"],
                    sucursal=u["sucursal"],
                    password_hash=generate_password_hash(u["pass"])
                )
                db.session.add(user_obj)
                db.session.flush()
            else:
                user_obj.password_hash = generate_password_hash(u["pass"])
                user_obj.rol = u["rol"]
                user_obj.sucursal = u["sucursal"]
            users[u["email"]] = user_obj
        db.session.commit()
        print("  -> 4 Usuarios listos (Admin, Vendedor 197, Vendedor 136, Bodega).")

        admin_user = users["admin@redcover.com"]
        vendedor_197 = users["vendedor@redcover.com"]
        vendedor_136 = users["vendedor136@redcover.com"]
        bodega_user = users["bodega@redcover.com"]

        # ----------------------------------------------------
        # 2. ASESORES DE VENTA
        # ----------------------------------------------------
        print("\n[2/13] Configurando Asesores de Ventas...")
        asesores_nombres = [
            "Juan Perez",
            "Carolina Gomez",
            "Andres Mendoza",
            "Valentina Rios",
            "Santiago Castro"
        ]
        asesores = {}
        for name in asesores_nombres:
            asesor = Asesor.query.filter_by(nombre=name).first()
            if not asesor:
                asesor = Asesor(nombre=name, activo=True)
                db.session.add(asesor)
                db.session.flush()
            asesores[name] = asesor
        db.session.commit()
        print(f"  -> {len(asesores)} Asesores comerciales activos creados.")

        # ----------------------------------------------------
        # 3. PROVEEDORES
        # ----------------------------------------------------
        print("\n[3/13] Configurando Proveedores...")
        providers_data = [
            {"nombre": "Distribuidora Celulares S.A.S", "empresa": "Distribuidora Celulares S.A.S", "telefono": "3109876543"},
            {"nombre": "Accesorios y Tecnologia Mayorista", "empresa": "Accesorios y Tecnologia Mayorista", "telefono": "3201234567"},
            {"nombre": "Importadora Global Tech", "empresa": "Global Tech Colombia", "telefono": "3145558899"},
            {"nombre": "MegaRepuestos Celulares", "empresa": "MegaRepuestos S.A.", "telefono": "3184442211"}
        ]
        providers = {}
        for p in providers_data:
            prov = Provider.query.filter_by(nombre=p["nombre"]).first()
            if not prov:
                prov = Provider(nombre=p["nombre"], empresa=p["empresa"], telefono=p["telefono"])
                db.session.add(prov)
                db.session.flush()
            providers[p["nombre"]] = prov
        db.session.commit()

        # Facturas y pagos a proveedores
        prov1 = providers["Distribuidora Celulares S.A.S"]
        if not ProviderInvoice.query.filter_by(provider_id=prov1.id, numero_factura="FAC-PROV-101").first():
            inv1 = ProviderInvoice(
                provider_id=prov1.id,
                monto_total=Decimal("8500000.00"),
                numero_factura="FAC-PROV-101",
                descripcion="Lote de 3 iPhones y 2 Samsung S24",
                fecha_factura=now - timedelta(days=10)
            )
            db.session.add(inv1)
            pay1 = ProviderPayment(
                provider_id=prov1.id,
                monto_abonado=Decimal("5000000.00"),
                observacion="Transferencia inicial Bancolombia 50%",
                fecha_pago=now - timedelta(days=5)
            )
            db.session.add(pay1)

        prov2 = providers["Accesorios y Tecnologia Mayorista"]
        if not ProviderInvoice.query.filter_by(provider_id=prov2.id, numero_factura="FAC-PROV-102").first():
            inv2 = ProviderInvoice(
                provider_id=prov2.id,
                monto_total=Decimal("1800000.00"),
                numero_factura="FAC-PROV-102",
                descripcion="Cargadores 20W, Cables C y AirPods",
                fecha_factura=now - timedelta(days=8)
            )
            db.session.add(inv2)
            pay2 = ProviderPayment(
                provider_id=prov2.id,
                monto_abonado=Decimal("1800000.00"),
                observacion="Pago total de contado factura 102",
                fecha_pago=now - timedelta(days=7)
            )
            db.session.add(pay2)
        db.session.commit()
        print("  -> Proveedores, facturas de compras y abonos vinculados.")

        # ----------------------------------------------------
        # 4. PRODUCTOS DE TIENDA Y VARIANTES (Inventario General)
        # ----------------------------------------------------
        print("\n[4/13] Configurando Inventario de Tienda & Variantes...")
        tienda_products = [
            {
                "sku": "ACC-001",
                "nombre": "Audifonos AirPods Pro 2da Gen",
                "stock": 18,
                "costo": Decimal("450000.00"),
                "minimo": Decimal("580000.00"),
                "sugerido": Decimal("650000.00"),
                "obs": "Cancelacion de ruido activa, estuche MagSafe USB-C"
            },
            {
                "sku": "ACC-002",
                "nombre": "Cargador Carga Rapida 20W Apple",
                "stock": 35,
                "costo": Decimal("45000.00"),
                "minimo": Decimal("65000.00"),
                "sugerido": Decimal("89000.00"),
                "obs": "Cubo original Apple tipo C"
            },
            {
                "sku": "ACC-003",
                "nombre": "Cable Trenzado USB-C a USB-C 60W",
                "stock": 40,
                "costo": Decimal("25000.00"),
                "minimo": Decimal("39000.00"),
                "sugerido": Decimal("49000.00"),
                "obs": "Ultra resistente 1 metro compatible con iPhone 15 y iPad"
            },
            {
                "sku": "ACC-004",
                "nombre": "Bateria Portatil MagSafe PowerBank 5000mAh",
                "stock": 12,
                "costo": Decimal("85000.00"),
                "minimo": Decimal("119000.00"),
                "sugerido": Decimal("145000.00"),
                "obs": "Carga inalambrica magnetica con soporte plegable"
            },
            {
                "sku": "ACC-005",
                "nombre": "Mica Hidrogel HD Mate / Transparente",
                "stock": 80,
                "costo": Decimal("6000.00"),
                "minimo": Decimal("15000.00"),
                "sugerido": Decimal("25000.00"),
                "obs": "Corte computarizado a medida para cualquier modelo"
            },
            {
                "sku": "ACC-006",
                "nombre": "Parlante Bluetooth JBL GO 3 Waterproof",
                "stock": 8,
                "costo": Decimal("140000.00"),
                "minimo": Decimal("185000.00"),
                "sugerido": Decimal("220000.00"),
                "obs": "Sonido potente Pro JBL, resistente al agua IP67"
            }
        ]

        products_map = {}
        for p in tienda_products:
            prod = Product.query.filter_by(sku=p["sku"]).first()
            if not prod:
                prod = Product(
                    nombre=p["nombre"],
                    sku=p["sku"],
                    tipo_inventario="tienda",
                    cantidad_stock=p["stock"],
                    precio_costo=p["costo"],
                    precio_minimo=p["minimo"],
                    precio_sugerido=p["sugerido"],
                    observacion=p["obs"]
                )
                db.session.add(prod)
                db.session.flush()
                # Registrar ajuste inicial
                adj = StockAdjustment(
                    product_id=prod.id,
                    admin_id=admin_user.id,
                    tipo_movimiento="Inventario Inicial Demo",
                    stock_anterior=0,
                    stock_nuevo=p["stock"]
                )
                db.session.add(adj)
            products_map[p["sku"]] = prod
        db.session.commit()

        # Producto con Variantes (Fundas Silicone Case)
        funda = Product.query.filter_by(sku="VAR-CASE-IP15").first()
        if not funda:
            funda = Product(
                nombre="Funda Silicone Case MagSafe iPhone 15 Pro Max",
                sku="VAR-CASE-IP15",
                tipo_inventario="tienda",
                cantidad_stock=24,
                precio_costo=Decimal("28000.00"),
                precio_minimo=Decimal("45000.00"),
                precio_sugerido=Decimal("60000.00"),
                observacion="Interior de microfibra y aro magnetico MagSafe fuerte"
            )
            db.session.add(funda)
            db.session.flush()

            variantes_data = [
                {"nombre": "Negro Medianoche", "stock": 8, "costo": 28000, "min": 45000, "sug": 60000},
                {"nombre": "Azul Tormenta", "stock": 6, "costo": 28000, "min": 45000, "sug": 60000},
                {"nombre": "Titanio Gris", "stock": 6, "costo": 28000, "min": 45000, "sug": 60000},
                {"nombre": "Cipres Verde", "stock": 4, "costo": 28000, "min": 45000, "sug": 60000}
            ]
            for v_item in variantes_data:
                v = ProductVariant(
                    product_id=funda.id,
                    nombre_variante=v_item["nombre"],
                    cantidad_stock=v_item["stock"],
                    precio_costo=Decimal(str(v_item["costo"])),
                    precio_minimo=Decimal(str(v_item["min"])),
                    precio_sugerido=Decimal(str(v_item["sug"]))
                )
                db.session.add(v)
            db.session.commit()
        products_map["VAR-CASE-IP15"] = funda
        print("  -> Accesorios generales y productos con variantes creados.")

        # ----------------------------------------------------
        # 5. MÓDULO DE CELULARES (Equipos Nuevos y Seminuevos)
        # ----------------------------------------------------
        print("\n[5/13] Configurando Modulo de Celulares (IMEIs)...")
        celulares_data = [
            {
                "sku": "CEL-DEMO-001",
                "nombre": "iPhone 15 Pro Max 256GB - Titanio Natural",
                "costo": Decimal("4300000.00"),
                "minimo": Decimal("4750000.00"),
                "sugerido": Decimal("4990000.00"),
                "imei": "358901234560001",
                "imei2": "358901234560002",
                "marca": "Apple",
                "modelo": "iPhone 15 Pro Max",
                "estado": "Nuevo",
                "color": "Titanio Natural",
                "bateria": "100%",
                "memoria": "256GB",
                "proveedor": "Distribuidora Celulares S.A.S",
                "inventario": "LOCAL 136",
                "obs": "Equipo sellado en caja original, garantia Apple 1 ano."
            },
            {
                "sku": "CEL-DEMO-002",
                "nombre": "iPhone 14 Pro 128GB - Morado Oscuro",
                "costo": Decimal("2850000.00"),
                "minimo": Decimal("3200000.00"),
                "sugerido": Decimal("3450000.00"),
                "imei": "358901234560003",
                "imei2": "358901234560004",
                "marca": "Apple",
                "modelo": "iPhone 14 Pro",
                "estado": "Usado",
                "color": "Deep Purple",
                "bateria": "92%",
                "memoria": "128GB",
                "proveedor": "Distribuidora Celulares S.A.S",
                "inventario": "LOCAL 136",
                "obs": "Excelente estado 9.5/10, libre de iCloud y operador."
            },
            {
                "sku": "CEL-DEMO-003",
                "nombre": "iPhone 13 128GB - Azul Medianoche",
                "costo": Decimal("1850000.00"),
                "minimo": Decimal("2150000.00"),
                "sugerido": Decimal("2350000.00"),
                "imei": "358901234560005",
                "imei2": "358901234560006",
                "marca": "Apple",
                "modelo": "iPhone 13",
                "estado": "Usado",
                "color": "Azul Medianoche",
                "bateria": "89%",
                "memoria": "128GB",
                "proveedor": "Distribuidora Celulares S.A.S",
                "inventario": "LOCAL 197",
                "obs": "100% funcional, incluye cargador y factura de garantia."
            },
            {
                "sku": "CEL-DEMO-004",
                "nombre": "Samsung Galaxy S24 Ultra 512GB - Titanium Gray",
                "costo": Decimal("3900000.00"),
                "minimo": Decimal("4400000.00"),
                "sugerido": Decimal("4700000.00"),
                "imei": "352345678900007",
                "imei2": "352345678900008",
                "marca": "Samsung",
                "modelo": "Galaxy S24 Ultra",
                "estado": "Nuevo",
                "color": "Titanium Gray",
                "bateria": "100%",
                "memoria": "512GB",
                "proveedor": "Distribuidora Celulares S.A.S",
                "inventario": "LOCAL 136",
                "obs": "Con S-Pen integrado, pantalla Dynamic AMOLED 2X."
            },
            {
                "sku": "CEL-DEMO-005",
                "nombre": "Xiaomi Redmi Note 13 Pro+ 5G 512GB",
                "costo": Decimal("1350000.00"),
                "minimo": Decimal("1650000.00"),
                "sugerido": Decimal("1820000.00"),
                "imei": "864501234560009",
                "imei2": "864501234560010",
                "marca": "Xiaomi",
                "modelo": "Redmi Note 13 Pro+",
                "estado": "Nuevo",
                "color": "Midnight Black",
                "bateria": "100%",
                "memoria": "512GB",
                "proveedor": "Distribuidora Celulares S.A.S",
                "inventario": "LOCAL 197",
                "obs": "Camara de 200MP con OIS, carga ultra rapida de 120W."
            }
        ]

        for cel in celulares_data:
            c_prod = Product.query.filter_by(sku=cel["sku"]).first()
            if not c_prod:
                c_prod = Product(
                    nombre=cel["nombre"],
                    sku=cel["sku"],
                    tipo_inventario="celulares",
                    cantidad_stock=1,
                    precio_costo=cel["costo"],
                    precio_minimo=cel["minimo"],
                    precio_sugerido=cel["sugerido"],
                    imei=cel["imei"],
                    imei2=cel["imei2"],
                    marca=cel["marca"],
                    modelo_celular=cel["modelo"],
                    estado_celular=cel["estado"],
                    color=cel["color"],
                    bateria=cel["bateria"],
                    memoria=cel["memoria"],
                    proveedor=cel["proveedor"],
                    inventario=cel["inventario"],
                    observacion=cel["obs"]
                )
                db.session.add(c_prod)
                db.session.flush()
            products_map[cel["sku"]] = c_prod
        db.session.commit()
        print("  -> Celulares de alta gama (Apple, Samsung, Xiaomi) cargados con IMEI.")

        # ----------------------------------------------------
        # 6. INVENTARIO DE BODEGA & CLIENTES MAYORISTAS
        # ----------------------------------------------------
        print("\n[6/13] Configurando Modulo Bodega y Cuentas por Cobrar...")
        bodega_prods = [
            {"sku": "BOD-I15PM-LOT", "nombre": "Lote iPhone 15 Pro Max 256GB (Bodega)", "stock": 15, "costo": 4300000, "min": 4600000, "sug": 4900000},
            {"sku": "BOD-S24U-LOT", "nombre": "Lote Samsung S24 Ultra (Bodega)", "stock": 10, "costo": 3800000, "min": 4100000, "sug": 4450000},
            {"sku": "BOD-CHG-PACK", "nombre": "Pack x10 Cargadores 20W Mayorista", "stock": 50, "costo": 380000, "min": 480000, "sug": 580000},
            {"sku": "BOD-PANT-IP13", "nombre": "Display Pantalla iPhone 13 OLED Calidad Original", "stock": 25, "costo": 220000, "min": 310000, "sug": 380000}
        ]
        for bp in bodega_prods:
            p_obj = Product.query.filter_by(sku=bp["sku"]).first()
            if not p_obj:
                p_obj = Product(
                    nombre=bp["nombre"],
                    sku=bp["sku"],
                    tipo_inventario="bodega",
                    cantidad_stock=bp["stock"],
                    precio_costo=Decimal(str(bp["costo"])),
                    precio_minimo=Decimal(str(bp["min"])),
                    precio_sugerido=Decimal(str(bp["sug"])),
                    observacion="Mercancia almacenada en Bodega Central para despacho mayorista."
                )
                db.session.add(p_obj)
                db.session.flush()
            products_map[bp["sku"]] = p_obj
        db.session.commit()

        # Clientes Mayoristas de Bodega
        clientes_bodega_data = [
            {
                "nit": "901.458.123-1",
                "nombre": "Distribuidora Tecnologica del Valle SAS",
                "telefono": "3185551234",
                "email": "compras@tecnovalle.com",
                "dir": "Carrera 5 # 14-32, Cali"
            },
            {
                "nit": "900.874.521-4",
                "nombre": "Celulares & Mas Bogota SAS",
                "telefono": "3103337788",
                "email": "gerencia@celularesymas.com.co",
                "dir": "Centro Comercial Unilago Local 2-114, Bogota"
            },
            {
                "nit": "1020485921",
                "nombre": "Andres Gomez (Tienda Movil Medellin)",
                "telefono": "3046669911",
                "email": "andres.movil@gmail.com",
                "dir": "Calle 10 # 43E-20, Medellin"
            }
        ]
        clientes_bodega = {}
        for c in clientes_bodega_data:
            cli = Cliente.query.filter_by(documento_o_nit=c["nit"]).first()
            if not cli:
                cli = Cliente(
                    nombre_o_razon_social=c["nombre"],
                    documento_o_nit=c["nit"],
                    telefono=c["telefono"],
                    email=c["email"],
                    direccion=c["dir"],
                    creado_por_id=admin_user.id
                )
                db.session.add(cli)
                db.session.flush()
            clientes_bodega[c["nit"]] = cli
        db.session.commit()

        # Facturas de Bodega (Crédito y Contado) y Abonos
        c_valle = clientes_bodega["901.458.123-1"]
        if not FacturaBodega.query.filter_by(numero_factura="FAC-BOD-001").first():
            fb1 = FacturaBodega(
                cliente_id=c_valle.id,
                usuario_id=bodega_user.id,
                numero_factura="FAC-BOD-001",
                monto_total=Decimal("9600000.00"),
                modalidad="credito",
                estado="Parcial",
                fecha_subida=now - timedelta(days=6)
            )
            db.session.add(fb1)
            db.session.flush()

            # Detalle factura bodega
            fbd1 = FacturaBodegaDetalle(
                factura_id=fb1.id,
                producto_id=products_map["BOD-I15PM-LOT"].id,
                cantidad=2,
                precio_venta=Decimal("4800000.00")
            )
            db.session.add(fbd1)

            # Abono registrado a la factura
            abono1 = AbonoBodega(
                cliente_id=c_valle.id,
                factura_id=fb1.id,
                usuario_id=admin_user.id,
                monto=Decimal("5000000.00"),
                metodo_pago="transferencia",
                observacion="Abono 50% por transferencia Bancolombia",
                fecha_abono=now - timedelta(days=2)
            )
            db.session.add(abono1)

        c_bogota = clientes_bodega["900.874.521-4"]
        if not FacturaBodega.query.filter_by(numero_factura="FAC-BOD-002").first():
            fb2 = FacturaBodega(
                cliente_id=c_bogota.id,
                usuario_id=bodega_user.id,
                numero_factura="FAC-BOD-002",
                monto_total=Decimal("2900000.00"),
                modalidad="contado",
                estado="Pagado",
                fecha_subida=now - timedelta(days=4)
            )
            db.session.add(fb2)
            db.session.flush()

            fbd2 = FacturaBodegaDetalle(
                factura_id=fb2.id,
                producto_id=products_map["BOD-CHG-PACK"].id,
                cantidad=5,
                precio_venta=Decimal("580000.00")
            )
            db.session.add(fbd2)
        db.session.commit()
        print("  -> Facturacion mayorista, carteras y abonos de clientes creados.")

        # ----------------------------------------------------
        # 7. INVENTARIO DE EXTERNOS (Productos Prestados de Otros Locales)
        # ----------------------------------------------------
        print("\n[7/13] Configurando Modulo Externos...")
        ext_cel = Product.query.filter_by(sku="EXT-CEL-001").first()
        if not ext_cel:
            ext_cel = Product(
                nombre="iPhone 13 Pro 256GB - Sierra Blue (Externo)",
                sku="EXT-CEL-001",
                tipo_inventario="externos",
                cantidad_stock=1,
                precio_costo=Decimal("2300000.00"),
                precio_minimo=Decimal("2650000.00"),
                precio_sugerido=Decimal("2850000.00"),
                imei="358901234569991",
                imei2="358901234569992",
                marca="Apple",
                modelo_celular="iPhone 13 Pro",
                estado_celular="Usado",
                color="Sierra Blue",
                bateria="87%",
                memoria="256GB",
                proveedor="Local Vecino 142",
                inventario="LOCAL 136",
                observacion="Prestado de Local 142 para venta directa"
            )
            db.session.add(ext_cel)
            db.session.flush()

        ext_acc = Product.query.filter_by(sku="EXTACC-001").first()
        if not ext_acc:
            ext_acc = Product(
                nombre="Display iPhone 14 Pro Max Original (Prestado)",
                sku="EXTACC-001",
                tipo_inventario="externos",
                cantidad_stock=2,
                precio_costo=Decimal("650000.00"),
                precio_minimo=Decimal("800000.00"),
                precio_sugerido=Decimal("950000.00"),
                observacion="Repuesto traido de Local 210 para arreglo urgente"
            )
            db.session.add(ext_acc)
            db.session.flush()
        db.session.commit()
        print("  -> Productos externos (celulares y repuestos) listos.")

        # ----------------------------------------------------
        # 8. HISTORIAL DE VENTAS (POS, Pagos Mixtos y Clientes)
        # ----------------------------------------------------
        print("\n[8/13] Creando Ventas de Demostracion con Multiples Metodos...")
        # Venta Demo 1: Venta Celular contado efectivo
        sale1_exist = Sale.query.filter_by(id=101).first()
        if not sale1_exist:
            s1 = Sale(
                id=101,
                vendedor_id=vendedor_136.id,
                asesor_id=asesores["Carolina Gomez"].id,
                monto_total=Decimal("3450000.00"),
                metodo_pago="efectivo",
                tipo_venta="celulares",
                sucursal="LOCAL 136",
                fecha_venta=now - timedelta(days=3, hours=4)
            )
            db.session.add(s1)
            db.session.flush()

            sd1 = SaleDetail(
                sale_id=s1.id,
                product_id=products_map["CEL-DEMO-002"].id,
                cantidad_vendida=1,
                precio_venta_final=Decimal("3450000.00")
            )
            db.session.add(sd1)

            sp1 = SalePayment(
                sale_id=s1.id,
                metodo_pago="efectivo",
                monto=Decimal("3450000.00")
            )
            db.session.add(sp1)

            sc1 = SaleClient(
                sale_id=s1.id,
                nombre="Carlos Eduardo Ramirez",
                documento="1025894120",
                telefono="3157894561",
                email="carlos.ramirez@outlook.com",
                direccion="Calle 45 # 13-28 Apto 402"
            )
            db.session.add(sc1)

        # Venta Demo 2: Pago Mixto (Nequi + Bancolombia + Efectivo)
        sale2_exist = Sale.query.filter_by(id=102).first()
        if not sale2_exist:
            s2 = Sale(
                id=102,
                vendedor_id=vendedor_197.id,
                asesor_id=asesores["Juan Perez"].id,
                monto_total=Decimal("828000.00"),
                metodo_pago="mixto",
                tipo_venta="general",
                sucursal="LOCAL 197",
                fecha_venta=now - timedelta(days=2, hours=2)
            )
            db.session.add(s2)
            db.session.flush()

            # AirPods + Cargador + Cable
            db.session.add(SaleDetail(sale_id=s2.id, product_id=products_map["ACC-001"].id, cantidad_vendida=1, precio_venta_final=Decimal("650000.00")))
            db.session.add(SaleDetail(sale_id=s2.id, product_id=products_map["ACC-002"].id, cantidad_vendida=1, precio_venta_final=Decimal("89000.00")))
            db.session.add(SaleDetail(sale_id=s2.id, product_id=products_map["ACC-003"].id, cantidad_vendida=1, precio_venta_final=Decimal("49000.00")))
            db.session.add(SaleDetail(sale_id=s2.id, product_id=products_map["ACC-005"].id, cantidad_vendida=1, precio_venta_final=Decimal("40000.00")))

            db.session.add(SalePayment(sale_id=s2.id, metodo_pago="nequi", monto=Decimal("300000.00")))
            db.session.add(SalePayment(sale_id=s2.id, metodo_pago="bancolombia", monto=Decimal("400000.00")))
            db.session.add(SalePayment(sale_id=s2.id, metodo_pago="efectivo", monto=Decimal("128000.00")))

            db.session.add(SaleClient(
                sale_id=s2.id,
                nombre="Laura Marcela Castano",
                documento="1037542109",
                telefono="3214569870",
                email="laura.castano@gmail.com",
                direccion="Cra 70 # 32-15"
            ))

        # Venta Demo 3: Venta con Producto Externo / Prestado
        sale3_exist = Sale.query.filter_by(id=103).first()
        if not sale3_exist:
            s3 = Sale(
                id=103,
                vendedor_id=admin_user.id,
                asesor_id=asesores["Andres Mendoza"].id,
                monto_total=Decimal("2800000.00"),
                metodo_pago="transferencia",
                tipo_venta="general",
                sucursal="LOCAL 136",
                fecha_venta=now - timedelta(days=1, hours=5)
            )
            db.session.add(s3)
            db.session.flush()

            sd3 = SaleDetail(
                sale_id=s3.id,
                product_id=None,
                nombre_manual="iPhone 13 Pro 256GB Sierra Blue (Prestado Local 142)",
                precio_costo_manual=Decimal("2300000.00"),
                cantidad_vendida=1,
                precio_venta_final=Decimal("2800000.00"),
                ok_contabilidad=True,
                ok_inventario=True
            )
            db.session.add(sd3)
            db.session.add(SalePayment(sale_id=s3.id, metodo_pago="bancolombia", monto=Decimal("2800000.00")))
            db.session.add(SaleClient(
                sale_id=s3.id,
                nombre="Felipe Henao Duque",
                documento="71239845",
                telefono="3117896541",
                email="felipe.henao@corp.co",
                direccion="Calle 10 sur # 25-40"
            ))
        db.session.commit()
        print("  -> Ventas de prueba (contado, pago mixto, producto externo) registradas.")

        # ----------------------------------------------------
        # 9. RETOMAS (Evaluación y Aprobadas)
        # ----------------------------------------------------
        print("\n[9/13] Configurando Modulo de Retomas...")
        # Retoma 1: En Evaluación (para demo de aprobación)
        ret1 = Retoma.query.filter_by(imei1="357890123450099").first()
        if not ret1:
            ret1 = Retoma(
                sale_id=101,
                modelo="iPhone 11 64GB",
                marca="Apple",
                proveedor="Cliente - Carlos Ramirez",
                valor_retoma=Decimal("750000.00"),
                arreglos=Decimal("80000.00"),
                imei1="357890123450099",
                imei2="357890123450098",
                color="Negro",
                bateria="83%",
                memoria="64GB",
                observaciones="Pantalla con micro-rayas leves. Bateria original en buen estado. Requiere limpieza de parlante.",
                estado="en_evaluacion",
                ok_contabilidad=False,
                ok_venta=False,
                vendedor_id=vendedor_136.id,
                fecha_registro=now - timedelta(days=2)
            )
            db.session.add(ret1)

        # Retoma 2: Ya aprobada e ingresada como producto usado
        ret2 = Retoma.query.filter_by(imei1="359988776655441").first()
        if not ret2:
            p_ret2 = Product.query.filter_by(sku="RET-DEMO-002").first()
            if not p_ret2:
                p_ret2 = Product(
                    nombre="iPhone 12 128GB - Blanco (Retoma)",
                    sku="RET-DEMO-002",
                    tipo_inventario="celulares",
                    inventario="LOCAL 136",
                    cantidad_stock=1,
                    precio_costo=Decimal("1250000.00"),
                    precio_minimo=Decimal("1500000.00"),
                    precio_sugerido=Decimal("1650000.00"),
                    imei="359988776655441",
                    imei2="359988776655442",
                    marca="Apple",
                    modelo_celular="iPhone 12",
                    estado_celular="Usado",
                    color="Blanco",
                    bateria="88%",
                    memoria="128GB",
                    proveedor="Cliente",
                    observacion="Retoma recibida y acondicionada. 100% operativa."
                )
                db.session.add(p_ret2)
                db.session.flush()

            ret2 = Retoma(
                sale_id=102,
                modelo="iPhone 12 128GB",
                marca="Apple",
                proveedor="Cliente - Laura Castano",
                valor_retoma=Decimal("1150000.00"),
                arreglos=Decimal("100000.00"),
                imei1="359988776655441",
                imei2="359988776655442",
                color="Blanco",
                bateria="88%",
                memoria="128GB",
                observaciones="Cambio de vidrio trasero realizado con exito. Equipo en vitrina.",
                estado="aprobado",
                ok_contabilidad=True,
                ok_venta=True,
                producto_generado_id=p_ret2.id if p_ret2 else None,
                vendedor_id=vendedor_197.id,
                fecha_registro=now - timedelta(days=4)
            )
            db.session.add(ret2)
        db.session.commit()
        print("  -> Retomas en cuarentena (evaluacion y aprobadas) registradas.")

        # ----------------------------------------------------
        # 10. MANEOS (Préstamos a Locales Vecinos)
        # ----------------------------------------------------
        print("\n[10/13] Configurando Modulo de Maneos (Prestamos)...")
        maneos_data = [
            {
                "prod_sku": "ACC-002",
                "local": "Local 142 - TecnoAccesorios",
                "cant": 2,
                "estado": "PENDIENTE",
                "dias": 1
            },
            {
                "prod_sku": "ACC-001",
                "local": "Local 210 - iStore Express",
                "cant": 1,
                "estado": "FACTURADO",
                "dias": 3
            },
            {
                "prod_sku": "ACC-003",
                "local": "Local 105 - Mundo Movil",
                "cant": 3,
                "estado": "DEVUELTO",
                "dias": 5
            }
        ]

        for m in maneos_data:
            target_p = products_map.get(m["prod_sku"])
            if target_p:
                exist_maneo = Maneo.query.filter_by(product_id=target_p.id, local_vecino=m["local"]).first()
                if not exist_maneo:
                    maneo_obj = Maneo(
                        product_id=target_p.id,
                        local_vecino=m["local"],
                        cantidad=m["cant"],
                        estado=m["estado"],
                        fecha_prestamo=now - timedelta(days=m["dias"]),
                        fecha_resolucion=(now - timedelta(days=m["dias"] - 1)) if m["estado"] != "PENDIENTE" else None
                    )
                    db.session.add(maneo_obj)
        db.session.commit()
        print("  -> Maneos (Pendiente, Facturado y Devuelto) creados.")

        # ----------------------------------------------------
        # 11. GASTOS (Operativos y Costos Indirectos)
        # ----------------------------------------------------
        print("\n[11/13] Configurando Modulo de Gastos...")
        gastos_data = [
            {"tipo": "Gasto Diario", "cat": "Alimentacion", "desc": "Almuerzo para personal de turno", "monto": 45000.0, "metodo": "efectivo", "suc": "LOCAL 136", "dias": 0},
            {"tipo": "Gasto Diario", "cat": "Transporte", "desc": "Taxi para retiro de repuestos en bodega", "monto": 22000.0, "metodo": "efectivo", "suc": "LOCAL 197", "dias": 1},
            {"tipo": "Gasto Diario", "cat": "Aseo y Cafeteria", "desc": "Insumos de limpieza y cafe para clientes", "monto": 38000.0, "metodo": "efectivo", "suc": "LOCAL 136", "dias": 2},
            {"tipo": "Costo Indirecto", "cat": "Arriendo", "desc": "Canon de arrendamiento Local 136", "monto": 2800000.0, "metodo": "bancolombia", "suc": "LOCAL 136", "dias": 5},
            {"tipo": "Costo Indirecto", "cat": "Servicios Publicos", "desc": "Internet Fibra Optica 500MB + Energia", "monto": 240000.0, "metodo": "nequi", "suc": "LOCAL 136", "dias": 6},
            {"tipo": "Costo Indirecto", "cat": "Publicidad", "desc": "Campana publicitaria Instagram Ads y TikTok", "monto": 350000.0, "metodo": "tarjeta", "suc": "LOCAL 136", "dias": 8}
        ]

        for g in gastos_data:
            if not Expense.query.filter_by(descripcion=g["desc"]).first():
                exp = Expense(
                    usuario_id=admin_user.id,
                    tipo_gasto=g["tipo"],
                    categoria=g["cat"],
                    descripcion=g["desc"],
                    monto=Decimal(str(g["monto"])),
                    metodo_pago=g["metodo"],
                    sucursal=g["suc"],
                    fecha_gasto=now - timedelta(days=g["dias"])
                )
                db.session.add(exp)
        db.session.commit()
        print("  -> Gastos diarios y costos fijos indirectos registrados.")

        # ----------------------------------------------------
        # 12. GARANTÍAS Y APROBACIONES DE PRECIOS
        # ----------------------------------------------------
        print("\n[12/13] Configurando Garantias y Aprobaciones de Precios...")
        # Garantía 1: Pendiente
        if not Warranty.query.filter_by(sale_id=101).first():
            w1 = Warranty(
                sale_id=101,
                product_id=products_map["CEL-DEMO-002"].id,
                quantity=1,
                reason="El cliente indica que el parlante frontal suena bajo luego de 2 dias de uso.",
                resolution="Pendiente",
                created_at=now - timedelta(days=1)
            )
            db.session.add(w1)

        # Garantía 2: Demorada (> 5 días)
        if not Warranty.query.filter_by(sale_id=102).first():
            w2 = Warranty(
                sale_id=102,
                product_id=products_map["ACC-001"].id,
                quantity=1,
                reason="Auricular izquierdo no carga dentro del estuche.",
                resolution="Pendiente",
                admin_notes="Enviado a revision de laboratorio tecnico central.",
                created_at=now - timedelta(days=7) # Dispara estado 'Demorado'
            )
            db.session.add(w2)

        # Garantía 3: Resuelta / Aprobada
        if not Warranty.query.filter_by(sale_id=103).first():
            w3 = Warranty(
                sale_id=103,
                nombre_manual="Cargador 20W Reemplazo",
                quantity=1,
                reason="Cable presentaba falso contacto de fabrica.",
                resolution="Aprobado",
                admin_notes="Se entrego unidad nueva al cliente sin costo adicional.",
                created_at=now - timedelta(days=4)
            )
            db.session.add(w3)

        # Aprobaciones de Precios
        # Aprobación 1: Pendiente
        if not PriceApproval.query.filter_by(precio_solicitado=Decimal("4700000.00")).first():
            pa1 = PriceApproval(
                vendedor_id=vendedor_136.id,
                product_id=products_map["CEL-DEMO-001"].id,
                precio_original=Decimal("4990000.00"),
                precio_solicitado=Decimal("4700000.00"),
                estado="pendiente",
                fecha_solicitud=now - timedelta(minutes=45)
            )
            db.session.add(pa1)

        # Aprobación 2: Aprobada
        if not PriceApproval.query.filter_by(precio_solicitado=Decimal("610000.00")).first():
            pa2 = PriceApproval(
                vendedor_id=vendedor_197.id,
                product_id=products_map["ACC-001"].id,
                precio_original=Decimal("650000.00"),
                precio_solicitado=Decimal("610000.00"),
                precio_aprobado=Decimal("610000.00"),
                estado="aprobada",
                admin_id=admin_user.id,
                fecha_solicitud=now - timedelta(hours=3),
                fecha_resolucion=now - timedelta(hours=2, minutes=50)
            )
            db.session.add(pa2)

        # Aprobación 3: Rechazada
        if not PriceApproval.query.filter_by(precio_solicitado=Decimal("1500000.00")).first():
            pa3 = PriceApproval(
                vendedor_id=vendedor_136.id,
                product_id=products_map["CEL-DEMO-003"].id,
                precio_original=Decimal("2350000.00"),
                precio_solicitado=Decimal("1500000.00"),
                estado="rechazada",
                admin_id=admin_user.id,
                motivo_rechazo="Precio solicitado esta por debajo del costo de adquisicion ($1.850.000).",
                fecha_solicitud=now - timedelta(hours=5),
                fecha_resolucion=now - timedelta(hours=4, minutes=30)
            )
            db.session.add(pa3)
        db.session.commit()
        print("  -> Garantias (Pendiente, Demorada, Resuelta) y Aprobaciones de Precios creadas.")

        # ----------------------------------------------------
        # 13. ARQUEOS DE CAJA Y SOBRANTES
        # ----------------------------------------------------
        print("\n[13/13] Configurando Arqueos de Caja y Registro de Sobrantes...")
        ayer = now.date() - timedelta(days=1)
        antier = now.date() - timedelta(days=2)

        # Arqueo 1: Local 136 de Ayer (Cerrado)
        arq1 = ArqueoCaja.query.filter_by(fecha_arqueo=ayer, sucursal="LOCAL 136", tipo_arqueo="general").first()
        if not arq1:
            arq1 = ArqueoCaja(
                vendedor_id=vendedor_136.id,
                fecha_arqueo=ayer,
                tipo_arqueo="general",
                sucursal="LOCAL 136",
                base_inicial=Decimal("200000.00"),
                gastos_del_dia=Decimal("45000.00"),
                observaciones_gastos="Gasto en almuerzos de turno",
                total_efectivo_sistema=Decimal("1450000.00"),
                total_transferencia_sistema=Decimal("2800000.00"),
                total_celulares=Decimal("2800000.00"),
                total_unidades_ch=Decimal("1450000.00"),
                efectivo_fisico=Decimal("1605000.00"),
                diferencia=Decimal("0.00"),
                observacion_diferencia="Caja cuadrada perfectamente sin novedades."
            )
            db.session.add(arq1)
            db.session.flush()

        # Arqueo 2: Local 197 de Antier con Sobrante Justificado
        arq2 = ArqueoCaja.query.filter_by(fecha_arqueo=antier, sucursal="LOCAL 197", tipo_arqueo="general").first()
        if not arq2:
            arq2 = ArqueoCaja(
                vendedor_id=vendedor_197.id,
                fecha_arqueo=antier,
                tipo_arqueo="general",
                sucursal="LOCAL 197",
                base_inicial=Decimal("150000.00"),
                gastos_del_dia=Decimal("22000.00"),
                observaciones_gastos="Taxi repuestos",
                total_efectivo_sistema=Decimal("800000.00"),
                total_transferencia_sistema=Decimal("700000.00"),
                efectivo_fisico=Decimal("948000.00"),
                diferencia=Decimal("20000.00"),
                observacion_diferencia="Sobrante de $20.000 por propina y redondeo de cliente."
            )
            db.session.add(arq2)
            db.session.flush()

            # Registrar en log de sobrantes
            sob = SobranteLog(
                arqueo_id=arq2.id,
                vendedor_id=vendedor_197.id,
                sucursal="LOCAL 197",
                fecha_arqueo=antier,
                monto_esperado=Decimal("928000.00"),
                efectivo_fisico=Decimal("948000.00"),
                monto_sobrante=Decimal("20000.00"),
                justificacion="Cliente dejo vuelto por excelente atencion en venta de funda."
            )
            db.session.add(sob)

        db.session.commit()
        print("  -> Arqueos historicos y registro de sobrantes completados.")

        print("\n==================================================")
        print("[OK] TODOS LOS MODULOS POBLADOS CON EXITO!")
        print("==================================================")

if __name__ == '__main__':
    seed_all()
