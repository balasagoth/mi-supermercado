# Importaciones necesarias de Django y otras librerías
import json
import stripe # Para la integración de pagos
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail

# Importaciones de nuestros modelos
from .models import Producto, Categoria, Pedido, DetallePedido, DisenoPersonalizado

# ==============================================================================
# VISTAS PÚBLICAS (Accesibles por todos los usuarios)
# ==============================================================================

def catalogo(request):
    """
    Muestra la página principal con el catálogo de productos.
    Permite filtrar por categoría y buscar por nombre.
    """
    # Obtener el objeto de diseño para pasar colores, logo, etc., a la plantilla
    try:
        diseno = DisenoPersonalizado.objects.first()
    except DisenoPersonalizado.DoesNotExist:
        diseno = None

    # Lógica de filtrado y búsqueda
    productos = Producto.objects.filter(disponible=True)
    categorias = Categoria.objects.all()
    
    query = request.GET.get('q')
    categoria_id = request.GET.get('categoria')

    if query:
        productos = productos.filter(nombre__icontains=query)
    
    if categoria_id:
        productos = productos.filter(categoria_id=categoria_id)

    context = {
        'productos': productos,
        'categorias': categorias,
        'diseno': diseno,
        'selected_categoria': int(categoria_id) if categoria_id else None,
    }
    return render(request, 'tienda/catalogo.html', context)


# ==============================================================================
# VISTAS DEL CARRITO DE COMPRAS (Manejo de la sesión)
# ==============================================================================

def vista_carrito(request):
    """
    Muestra el contenido del carrito de compras y calcula los totales.
    """
    carrito = request.session.get('carrito', {})
    items_carrito = []
    subtotal_carrito = 0

    for producto_id, item_data in carrito.items():
        producto = get_object_or_404(Producto, id=producto_id)
        total_item = producto.precio * item_data['cantidad']
        items_carrito.append({
            'producto': producto,
            'cantidad': item_data['cantidad'],
            'total_item': total_item
        })
        subtotal_carrito += total_item
    
    # Ejemplo de cálculo de impuesto (ej: 19%)
    impuesto = subtotal_carrito * 0.19
    total_final = subtotal_carrito + impuesto
    
    context = {
        'items_carrito': items_carrito,
        'subtotal_carrito': subtotal_carrito,
        'impuesto': impuesto,
        'total_final': total_final,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY
    }
    return render(request, 'tienda/carrito.html', context)


@require_POST
def agregar_al_carrito(request):
    """
    Añade un producto al carrito (usando Fetch/AJAX desde el frontend).
    """
    data = json.loads(request.body)
    producto_id = str(data.get('producto_id'))
    producto = get_object_or_404(Producto, id=producto_id)
    
    carrito = request.session.get('carrito', {})
    
    if producto.stock <= 0:
        return JsonResponse({'error': 'Producto sin stock'}, status=400)
    
    if producto_id in carrito:
        if producto.stock > carrito[producto_id]['cantidad']:
            carrito[producto_id]['cantidad'] += 1
        else:
            return JsonResponse({'error': 'No hay suficiente stock'}, status=400)
    else:
        carrito[producto_id] = {'cantidad': 1}
        
    request.session['carrito'] = carrito
    messages.success(request, f'"{producto.nombre}" fue añadido a tu carrito.')
    return JsonResponse({'mensaje': f'{producto.nombre} añadido al carrito.', 'total_items': sum(item['cantidad'] for item in carrito.values())})


@require_POST
def actualizar_carrito(request):
    """
    Actualiza la cantidad de un producto en el carrito o lo elimina si la cantidad es 0.
    """
    data = json.loads(request.body)
    producto_id = str(data.get('producto_id'))
    cantidad = int(data.get('cantidad'))
    
    carrito = request.session.get('carrito', {})
    
    if producto_id in carrito:
        if cantidad > 0:
            carrito[producto_id]['cantidad'] = cantidad
        else:
            del carrito[producto_id] # Eliminar si la cantidad es 0 o menos
        
        request.session['carrito'] = carrito
        return JsonResponse({'mensaje': 'Carrito actualizado.'})
    
    return JsonResponse({'error': 'Producto no encontrado en el carrito'}, status=404)


# ==============================================================================
# PROCESO DE CHECKOUT Y PAGOS (Integración con Stripe)
# ==============================================================================

@login_required
def crear_sesion_pago(request):
    """
    Crea una sesión de pago en Stripe y redirige al usuario a la pasarela de pago.
    """
    carrito = request.session.get('carrito', {})
    if not carrito:
        messages.error(request, "Tu carrito está vacío.")
        return redirect('vista_carrito')

    line_items = []
    for producto_id, item_data in carrito.items():
        producto = get_object_or_404(Producto, id=producto_id)
        line_items.append({
            'price_data': {
                'currency': 'usd', # Cambiar a tu moneda local (ej: 'eur', 'mxn')
                'product_data': {
                    'name': producto.nombre,
                    'images': [request.build_absolute_uri(producto.imagen.url)],
                },
                'unit_amount': int(producto.precio * 100), # Stripe usa centavos
            },
            'quantity': item_data['cantidad'],
        })

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            success_url=request.build_absolute_uri('/pedido/exitoso/'),
            cancel_url=request.build_absolute_uri('/carrito/'),
            metadata={
                'user_id': request.user.id,
                'carrito': json.dumps(carrito) # Guardamos el carrito para el webhook
            }
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        messages.error(request, f"Error al conectar con la pasarela de pago: {e}")
        return redirect('vista_carrito')

def pedido_exitoso(request):
    """

    Página a la que es redirigido el usuario tras un pago exitoso.
    El pedido real se crea a través del webhook para mayor seguridad.
    """
    # Se podría mostrar un mensaje genérico mientras el webhook procesa el pedido.
    # El carrito se vacía en el webhook después de crear el pedido.
    return render(request, 'tienda/pedido_confirmado.html')


@csrf_exempt
def stripe_webhook(request):
    """
    Escucha eventos de Stripe, específicamente cuando un pago se completa.
    Esta es la forma SEGURA de procesar un pedido, ya que confirma que el pago fue real.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    event = None

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return HttpResponse(status=400) # Payload inválido
    except stripe.error.SignatureVerificationError:
        return HttpResponse(status=400) # Firma inválida

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # Extraer metadatos
        user_id = session.metadata['user_id']
        carrito = json.loads(session.metadata['carrito'])
        user = get_object_or_404(User, id=user_id)
        
        # Evitar crear pedidos duplicados si el webhook se envía varias veces
        if Pedido.objects.filter(id_transaccion_pago=session.id).exists():
            return HttpResponse(status=200)

        # 1. Crear el objeto Pedido
        pedido = Pedido.objects.create(
            usuario=user,
            total=session.amount_total / 100.0,
            estado='En preparación',
            id_transaccion_pago=session.id
        )
        
        # 2. Crear los Detalles del Pedido y actualizar stock
        for producto_id, item_data in carrito.items():
            producto = get_object_or_404(Producto, id=producto_id)
            cantidad = item_data['cantidad']
            
            DetallePedido.objects.create(
                pedido=pedido,
                producto=producto,
                cantidad=cantidad,
                precio_unitario=producto.precio
            )
            # Actualizar stock
            producto.stock -= cantidad
            producto.save()
        
        # 3. Enviar correos de confirmación
        # (Descomentar y configurar SMTP en settings.py para que funcione)
        # send_mail(
        #     subject=f'Confirmación de tu Pedido #{pedido.id}',
        #     message=f'Hola {user.first_name},\n\nTu pedido ha sido confirmado y está en preparación.\nGracias por tu compra.',
        #     from_email=settings.DEFAULT_FROM_EMAIL,
        #     recipient_list=[user.email],
        # )

        # 4. Vaciar el carrito de la sesión
        # Esto es un desafío porque el webhook no tiene acceso a la sesión del usuario.
        # Una estrategia es marcar el pedido como "pagado" y que la vista de "éxito"
        # vacíe el carrito si el último pedido del usuario está pagado.
        
    return HttpResponse(status=200)


# ==============================================================================
# VISTAS DEL PERFIL DE USUARIO
# ==============================================================================

@login_required
def historial_pedidos(request):
    """
    Muestra el historial de pedidos del usuario que ha iniciado sesión.
    """
    pedidos = Pedido.objects.filter(usuario=request.user).order_by('-fecha_pedido')
    context = {
        'pedidos': pedidos
    }
    return render(request, 'tienda/historial.html', context)
