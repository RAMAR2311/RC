import os
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from functools import wraps
from datetime import date, datetime, timedelta
from sqlalchemy import func

from models import (
    db, Sale, SaleDetail, SalePayment, Product, ProductVariant,
    Retoma, ArqueoCaja, SobranteLog, Expense, Cliente, FacturaBodega,
    AbonoBodega, Provider, ProviderInvoice, ProviderPayment,
    Warranty, Maneo, PriceApproval, Asesor, User, StockAdjustment
)

zenic_bp = Blueprint('zenic_bp', __name__, template_folder='../templates')

# ── Decorador: solo administradores ─────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != 'admin':
            return jsonify({'error': 'Acceso restringido al administrador.'}), 403
        return f(*args, **kwargs)
    return decorated


# ── Recolector de contexto del sistema ──────────────────────────────────────
def _recolectar_contexto():
    """Recopila un resumen completo del sistema para inyectar como contexto al LLM."""
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)

    bloques = []

    # ── 1. VENTAS ────────────────────────────────────────────────────────────
    try:
        ventas_hoy = Sale.query.filter(
            func.date(Sale.fecha_venta) == hoy
        ).all()
        total_hoy = sum(float(v.monto_total or 0) for v in ventas_hoy)

        ventas_mes = Sale.query.filter(
            Sale.fecha_venta >= datetime.combine(inicio_mes, datetime.min.time())
        ).all()
        total_mes = sum(float(v.monto_total or 0) for v in ventas_mes)

        # Desglose por método de pago (hoy)
        pagos_hoy = {}
        for v in ventas_hoy:
            if v.pagos:
                for p in v.pagos:
                    m = p.metodo_pago.lower()
                    pagos_hoy[m] = pagos_hoy.get(m, 0) + float(p.monto or 0)
            else:
                m = (v.metodo_pago or 'efectivo').lower()
                pagos_hoy[m] = pagos_hoy.get(m, 0) + float(v.monto_total or 0)

        desglose_pago = ', '.join(
            f"{k}: ${v:,.0f}" for k, v in pagos_hoy.items()
        ) or 'Sin ventas'

        # Ventas por sucursal (mes)
        por_sucursal = {}
        for v in ventas_mes:
            s = v.sucursal or 'Sin sucursal'
            por_sucursal[s] = por_sucursal.get(s, 0) + float(v.monto_total or 0)

        sucursal_txt = ', '.join(
            f"{k}: ${v:,.0f}" for k, v in por_sucursal.items()
        ) or 'N/A'

        bloques.append(f"""
=== VENTAS ===
- Ventas hoy ({hoy}): {len(ventas_hoy)} transacciones | Total: ${total_hoy:,.0f}
- Desglose pago hoy: {desglose_pago}
- Ventas este mes ({inicio_mes} al {hoy}): {len(ventas_mes)} transacciones | Total: ${total_mes:,.0f}
- Por sucursal (mes): {sucursal_txt}
""")
    except Exception as e:
        bloques.append(f"=== VENTAS ===\nError al leer: {e}\n")

    # ── 2. INVENTARIO ACCESORIOS / TIENDA ────────────────────────────────────
    try:
        productos_tienda = Product.query.filter(
            Product.tipo_inventario.in_(['tienda', 'bodega'])
        ).all()

        total_productos = len(productos_tienda)
        sin_stock = [p for p in productos_tienda if p.total_stock == 0]
        stock_bajo = [p for p in productos_tienda if 0 < p.total_stock <= 5]
        valor_inventario = sum(
            float(p.precio_costo or 0) * p.total_stock for p in productos_tienda
        )

        sin_stock_txt = ', '.join(p.nombre for p in sin_stock[:10]) or 'Ninguno'
        stock_bajo_txt = ', '.join(
            f"{p.nombre} ({p.total_stock})" for p in stock_bajo[:10]
        ) or 'Ninguno'

        bloques.append(f"""
=== INVENTARIO ACCESORIOS/TIENDA ===
- Total productos registrados: {total_productos}
- Productos sin stock: {len(sin_stock)} → {sin_stock_txt}
- Stock bajo (1-5 uds): {len(stock_bajo)} → {stock_bajo_txt}
- Valor estimado inventario (costo): ${valor_inventario:,.0f}
""")
    except Exception as e:
        bloques.append(f"=== INVENTARIO ===\nError al leer: {e}\n")

    # ── 3. INVENTARIO CELULARES ───────────────────────────────────────────────
    try:
        celulares = Product.query.filter_by(tipo_inventario='celulares').all()
        cel_disponibles = [c for c in celulares if c.total_stock > 0]
        cel_marcas = {}
        for c in cel_disponibles:
            m = c.marca or 'Sin marca'
            cel_marcas[m] = cel_marcas.get(m, 0) + 1

        marcas_txt = ', '.join(
            f"{k}: {v}" for k, v in sorted(cel_marcas.items(), key=lambda x: -x[1])[:8]
        ) or 'N/A'

        valor_cel = sum(
            float(c.precio_costo or 0) * c.total_stock for c in cel_disponibles
        )

        bloques.append(f"""
=== INVENTARIO CELULARES ===
- Total celulares registrados: {len(celulares)}
- Disponibles en stock: {len(cel_disponibles)}
- Por marca: {marcas_txt}
- Valor estimado inventario celulares (costo): ${valor_cel:,.0f}
""")
    except Exception as e:
        bloques.append(f"=== CELULARES ===\nError al leer: {e}\n")

    # ── 4. RETOMAS ───────────────────────────────────────────────────────────
    try:
        retomas = Retoma.query.all()
        en_evaluacion = [r for r in retomas if r.estado == 'en_evaluacion']
        aprobadas = [r for r in retomas if r.estado == 'aprobado']
        pendientes_contabilidad = [r for r in retomas if not r.ok_contabilidad]
        pendientes_venta = [r for r in retomas if not r.ok_venta]
        valor_retomas = sum(float(r.valor_retoma or 0) for r in retomas)
        valor_arreglos = sum(float(r.arreglos or 0) for r in retomas)

        bloques.append(f"""
=== RETOMAS ===
- Total retomas registradas: {len(retomas)}
- En evaluación (cuarentena): {len(en_evaluacion)}
- Aprobadas: {len(aprobadas)}
- Pendientes ok contabilidad: {len(pendientes_contabilidad)}
- Pendientes ok venta: {len(pendientes_venta)}
- Valor total retomas: ${valor_retomas:,.0f}
- Valor total arreglos: ${valor_arreglos:,.0f}
""")
    except Exception as e:
        bloques.append(f"=== RETOMAS ===\nError al leer: {e}\n")

    # ── 5. ARQUEO DE CAJA ────────────────────────────────────────────────────
    try:
        ultimo_arqueo = ArqueoCaja.query.order_by(ArqueoCaja.fecha_creacion.desc()).first()
        arqueos_mes = ArqueoCaja.query.filter(
            ArqueoCaja.fecha_arqueo >= inicio_mes
        ).all()

        if ultimo_arqueo:
            arq_info = (
                f"Fecha: {ultimo_arqueo.fecha_arqueo} | "
                f"Sucursal: {ultimo_arqueo.sucursal} | "
                f"Efectivo sistema: ${float(ultimo_arqueo.total_efectivo_sistema or 0):,.0f} | "
                f"Efectivo físico: ${float(ultimo_arqueo.efectivo_fisico or 0):,.0f} | "
                f"Diferencia: ${float(ultimo_arqueo.diferencia or 0):,.0f}"
            )
        else:
            arq_info = 'Sin arqueos registrados'

        dif_acum = sum(float(a.diferencia or 0) for a in arqueos_mes)

        bloques.append(f"""
=== ARQUEO DE CAJA ===
- Último arqueo: {arq_info}
- Arqueos este mes: {len(arqueos_mes)}
- Diferencia acumulada del mes: ${dif_acum:,.0f}
""")
    except Exception as e:
        bloques.append(f"=== ARQUEO ===\nError al leer: {e}\n")

    # ── 6. GASTOS ────────────────────────────────────────────────────────────
    try:
        gastos_mes = Expense.query.filter(
            Expense.fecha_gasto >= datetime.combine(inicio_mes, datetime.min.time())
        ).all()

        total_gastos_mes = sum(float(g.monto or 0) for g in gastos_mes)
        por_categoria = {}
        for g in gastos_mes:
            cat = g.categoria or 'Sin categoría'
            por_categoria[cat] = por_categoria.get(cat, 0) + float(g.monto or 0)

        cat_txt = ', '.join(
            f"{k}: ${v:,.0f}" for k, v in sorted(
                por_categoria.items(), key=lambda x: -x[1]
            )[:8]
        ) or 'Sin gastos'

        gastos_hoy = [g for g in gastos_mes if g.fecha_gasto.date() == hoy]
        total_gastos_hoy = sum(float(g.monto or 0) for g in gastos_hoy)

        bloques.append(f"""
=== GASTOS ===
- Gastos hoy: {len(gastos_hoy)} registros | Total: ${total_gastos_hoy:,.0f}
- Gastos este mes: {len(gastos_mes)} registros | Total: ${total_gastos_mes:,.0f}
- Por categoría (mes): {cat_txt}
""")
    except Exception as e:
        bloques.append(f"=== GASTOS ===\nError al leer: {e}\n")

    # ── 7. CLIENTES BODEGA ───────────────────────────────────────────────────
    try:
        clientes = Cliente.query.all()
        con_deuda = [c for c in clientes if c.deuda_total > 0]
        deuda_total_cartera = sum(float(c.deuda_total) for c in con_deuda)

        bloques.append(f"""
=== CLIENTES (BODEGA) ===
- Total clientes registrados: {len(clientes)}
- Clientes con deuda pendiente: {len(con_deuda)}
- Cartera total por cobrar: ${deuda_total_cartera:,.0f}
""")
    except Exception as e:
        bloques.append(f"=== CLIENTES ===\nError al leer: {e}\n")

    # ── 8. PROVEEDORES ────────────────────────────────────────────────────────
    try:
        proveedores = Provider.query.all()
        con_saldo = [p for p in proveedores if float(p.saldo_pendiente or 0) > 0]
        deuda_prov = sum(float(p.saldo_pendiente or 0) for p in con_saldo)

        prov_txt = ', '.join(
            f"{p.nombre} (${float(p.saldo_pendiente or 0):,.0f})" for p in con_saldo[:6]
        ) or 'Ninguno'

        bloques.append(f"""
=== PROVEEDORES ===
- Total proveedores: {len(proveedores)}
- Proveedores con saldo pendiente: {len(con_saldo)}
- Deuda total a proveedores: ${deuda_prov:,.0f}
- Detalle: {prov_txt}
""")
    except Exception as e:
        bloques.append(f"=== PROVEEDORES ===\nError al leer: {e}\n")

    # ── 9. GARANTÍAS ─────────────────────────────────────────────────────────
    try:
        garantias = Warranty.query.all()
        pendientes = [g for g in garantias if g.resolution.lower() == 'pendiente']
        demoradas = [g for g in garantias if g.estado_actual == 'Demorado']

        bloques.append(f"""
=== GARANTÍAS ===
- Total garantías registradas: {len(garantias)}
- Pendientes de resolución: {len(pendientes)}
- Demoradas (>5 días sin resolver): {len(demoradas)}
""")
    except Exception as e:
        bloques.append(f"=== GARANTÍAS ===\nError al leer: {e}\n")

    # ── 10. MANEOS ────────────────────────────────────────────────────────────
    try:
        maneos = Maneo.query.all()
        pendientes_m = [m for m in maneos if m.estado == 'PENDIENTE']

        bloques.append(f"""
=== MANEOS (PRÉSTAMOS ENTRE LOCALES) ===
- Total maneos registrados: {len(maneos)}
- Maneos pendientes de resolución: {len(pendientes_m)}
""")
    except Exception as e:
        bloques.append(f"=== MANEOS ===\nError al leer: {e}\n")

    # ── 11. APROBACIONES DE PRECIO ────────────────────────────────────────────
    try:
        aprobaciones = PriceApproval.query.filter_by(estado='pendiente').all()
        bloques.append(f"""
=== APROBACIONES DE PRECIO ===
- Solicitudes de aprobación de precio pendientes: {len(aprobaciones)}
""")
    except Exception as e:
        bloques.append(f"=== APROBACIONES ===\nError al leer: {e}\n")

    # ── 12. PERSONAL ──────────────────────────────────────────────────────────
    try:
        usuarios = User.query.all()
        asesores = Asesor.query.filter_by(activo=True).all()

        bloques.append(f"""
=== PERSONAL ===
- Usuarios del sistema: {len(usuarios)}
- Asesores activos: {len(asesores)}
""")
    except Exception as e:
        bloques.append(f"=== PERSONAL ===\nError al leer: {e}\n")

    # ── CONTEXTO FINAL ────────────────────────────────────────────────────────
    fecha_hora = datetime.now().strftime('%Y-%m-%d %H:%M')
    encabezado = (
        f"Eres ZENIC, el asistente de inteligencia artificial del sistema de gestión RedCover "
        f"(tienda de telefonía y accesorios en Colombia). "
        f"Fecha y hora actual: {fecha_hora}. "
        f"Tienes acceso a los siguientes datos en tiempo real del sistema. "
        f"Responde siempre en español, de forma clara, concisa y profesional. "
        f"Usa los datos disponibles para dar análisis precisos. "
        f"Si la pregunta no está relacionada con el negocio, redirige al usuario gentilmente.\n\n"
        f"DATOS DEL SISTEMA:\n"
    )

    return encabezado + '\n'.join(bloques)


# ── Rutas ────────────────────────────────────────────────────────────────────
@zenic_bp.route('/')
@login_required
@admin_required
def index():
    return render_template('zenic/chat.html')


@zenic_bp.route('/chat', methods=['POST'])
@login_required
@admin_required
def chat():
    """Endpoint principal: recibe el mensaje del usuario + historial y consulta OpenAI."""
    data = request.get_json(silent=True) or {}
    mensaje_usuario = (data.get('mensaje') or '').strip()
    historial = data.get('historial', [])  # lista de {role, content}

    if not mensaje_usuario:
        return jsonify({'error': 'Mensaje vacío.'}), 400

    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return jsonify({
            'error': 'La variable de entorno OPENAI_API_KEY no está configurada.'
        }), 500

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        # Construir el system prompt con datos del sistema
        system_prompt = _recolectar_contexto()

        # Armar mensajes: system + historial previo + nuevo mensaje del usuario
        messages = [{'role': 'system', 'content': system_prompt}]

        # Incluir hasta los últimos 10 turnos del historial para mantener contexto
        for turno in historial[-10:]:
            if turno.get('role') in ('user', 'assistant') and turno.get('content'):
                messages.append({'role': turno['role'], 'content': turno['content']})

        messages.append({'role': 'user', 'content': mensaje_usuario})

        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=messages,
            max_tokens=1024,
            temperature=0.4,
        )

        respuesta = response.choices[0].message.content

        return jsonify({
            'respuesta': respuesta,
            'tokens_usados': response.usage.total_tokens if response.usage else None
        })

    except Exception as e:
        return jsonify({'error': f'Error al contactar OpenAI: {str(e)}'}), 500
