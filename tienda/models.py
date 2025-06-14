from django.db import models
from django.contrib.auth.models import User

# ==============================================================================
# 1. MODELO PARA LA PERSONALIZACIÓN DEL DISEÑO
# Esta tabla almacenará una única fila con las opciones de diseño que
# el administrador puede cambiar desde su panel.
# ==============================================================================
class DisenoPersonalizado(models.Model):
    """
    Modelo para que el administrador pueda personalizar la apariencia del sitio.
    Se limita a una sola instancia para que solo haya una configuración global.
    """
    color_primario = models.CharField(
        max_length=7, 
        default='#0D6EFD', 
        help_text="Color principal para botones y la barra de navegación (formato hexadecimal, ej: #FF5733)."
    )
    fuente_principal = models.CharField(
        max_length=100, 
        default='Arial, sans-serif', 
        help_text="Familia de fuentes para el cuerpo del texto (ej: 'Roboto', 'Verdana')."
    )
    logo = models.ImageField(
        upload_to='design/', 
        blank=True, 
        null=True, 
        help_text="Logo que aparecerá en la barra de navegación."
    )
    banner_principal = models.ImageField(
        upload_to='design/', 
        blank=True, 
        null=True, 
        help_text="Banner grande para la página de inicio (para promociones)."
    )

    def __str__(self):
        return "Configuración de Diseño del Sitio"

    class Meta:
        # Esto hace que en el panel de admin aparezca con un nombre más amigable.
        verbose_name = "1. Personalización de Diseño"
        verbose_name_plural = "1. Personalización de Diseño"


# ==============================================================================
# 2. MODELO PARA LAS CATEGORÍAS DE PRODUCTOS
# Esto nos permite organizar los productos (Lácteos, Frutas, Limpieza, etc.)
# ==============================================================================
class Categoria(models.Model):
    """
    Categorías para agrupar productos. Ejemplos: Lácteos, Panadería, Bebidas.
    """
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, help_text="Descripción opcional de la categoría.")

    def __str__(self):
        return self.nombre

    class Meta:
        verbose_name = "Categoría de Producto"
        verbose_name_plural = "2. Categorías de Productos"


# ==============================================================================
# 3. MODELO PARA LOS PRODUCTOS
# El corazón de la tienda. Aquí se define cada artículo que se vende.
# ==============================================================================
class Producto(models.Model):
    """
    Representa un artículo individual en el inventario del supermercado.
    """
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField()
    precio = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text="Precio de venta al público."
    )
    stock = models.PositiveIntegerField(
        default=0, 
        help_text="Cantidad de unidades disponibles en inventario."
    )
    # La relación ForeignKey conecta cada producto a una categoría.
    # on_delete=models.SET_NULL significa que si se borra una categoría,
    # los productos asociados no se borran, simplemente se quedan sin categoría.
    categoria = models.ForeignKey(Categoria, related_name='productos', on_delete=models.SET_NULL, null=True, blank=True)
    imagen = models.ImageField(
        upload_to='productos/', 
        default='productos/default.png', 
        help_text="Imagen principal del producto."
    )
    disponible = models.BooleanField(
        default=True, 
        help_text="Marca si el producto está visible y se puede comprar."
    )
    fecha_ingreso = models.DateTimeField(
        auto_now_add=True, 
        help_text="Fecha y hora en que se creó el producto en el sistema."
    )

    def __str__(self):
        return f"{self.nombre} (${self.precio})"

    class Meta:
        ordering = ['nombre'] # Ordena los productos alfabéticamente por defecto.
        verbose_name = "Producto"
        verbose_name_plural = "3. Productos"


# ==============================================================================
# 4. MODELO PARA LOS PEDIDOS (ÓRDENES DE COMPRA)
# Almacena la información general de una compra realizada por un usuario.
# ==============================================================================
class Pedido(models.Model):
    """
    Almacena una orden de compra completa, asociada a un usuario.
    """
    ESTADO_CHOICES = [
        ('Pendiente', 'Pendiente'),
        ('En preparación', 'En preparación'),
        ('Enviado', 'Enviado'),
        ('Entregado', 'Entregado'),
        ('Cancelado', 'Cancelado'),
    ]
    
    # on_delete=models.CASCADE significa que si un usuario es borrado,
    # todos sus pedidos también se borrarán.
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pedidos')
    fecha_pedido = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='Pendiente')
    total = models.DecimalField(max_digits=10, decimal_places=2)
    direccion_envio = models.CharField(max_length=255, blank=True, help_text="Dirección de envío para este pedido.")
    id_transaccion_pago = models.CharField(max_length=100, blank=True, help_text="ID de la transacción de la pasarela de pago (ej: Stripe).")

    def __str__(self):
        return f"Pedido #{self.id} de {self.usuario.username} - {self.estado}"

    class Meta:
        ordering = ['-fecha_pedido'] # Los pedidos más recientes aparecerán primero.
        verbose_name = "Pedido"
        verbose_name_plural = "4. Pedidos"


# ==============================================================================
# 5. MODELO PARA EL DETALLE DE CADA PEDIDO
# Es una tabla intermedia que conecta un Pedido con los Productos que contiene.
# ==============================================================================
class DetallePedido(models.Model):
    """
    Representa un ítem específico dentro de un Pedido (un producto y su cantidad).
    """
    # related_name='detalles' nos permite acceder desde un objeto Pedido
    # a todos sus detalles usando `pedido.detalles.all()`
    pedido = models.ForeignKey(Pedido, related_name='detalles', on_delete=models.CASCADE)
    
    # on_delete=models.PROTECT evita que un producto pueda ser borrado si forma
    # parte de un pedido ya realizado. Es una medida de seguridad de datos.
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Precio del producto en el momento de la compra."
    )

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre} en Pedido #{self.pedido.id}"

    def get_subtotal(self):
        return self.cantidad * self.precio_unitario

    class Meta:
        # Asegura que no se pueda añadir el mismo producto dos veces en el mismo pedido.
        # En su lugar, se debería actualizar la cantidad del ítem existente.
        unique_together = ('pedido', 'producto')
        verbose_name = "Detalle de Pedido"
        verbose_name_plural = "Detalles de Pedidos"
