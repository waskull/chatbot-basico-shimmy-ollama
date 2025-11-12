from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from django.contrib.auth.models import User
from rest_framework_simplejwt.authentication import JWTAuthentication
from chatbot.models import Conversacion, Documento
from chatbot.serializers import ConversacionSerializer, DocumentoSerializer
from django.conf import settings
import httpx
from chatbot.rag import generar_respuesta, generar_respuesta_llamacpp


class DocumentView(APIView):
    serializer_class = DocumentoSerializer
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        serializer = DocumentoSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChatbotView(APIView):
    serializer_class = ConversacionSerializer
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        engine = request.query_params.get('engine', "ollama").lower()
        pregunta = serializer.validated_data["pregunta"].lower()
        documentos = Documento.objects.all()
        contexto = "\n".join([f"{d.titulo}:\n{d.contenido}\n" for d in documentos])

        SYSTEM_PROMPT = (
            "Eres el asistente del sistema de envio de paquetes JulioN. "
            "Usa solo la información provista en el 'CONTEXT' para responder "
            "consultas sobre reglas o procedimientos, metodos de pago, tiempos de entrega y articulos prohibidos. "
            "Si no puedes responder con la información disponible, indica que no puedes responder."
        )
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"=== CONTEXT ===\n{contexto}\n\n"
            f"=== PREGUNTA DEL USUARIO ===\n{pregunta}\n\n"
            "=== INSTRUCCIÓN ===\n"
            "Responde solo con información del contexto. Sé claro, conciso y emite la respuesta en texto plano.\n"
        )
        temperatura = serializer.validated_data.get("temperatura", 0.8)
        modelo = serializer.validated_data.get("modelo", settings.MODEL_NAME)
        try:
            print("Haciendo petición a Ollama con el modelo:", modelo)
            print("Prompt:", prompt)
            print("Engine:", engine)
            respuesta = generar_respuesta(prompt, modelo, temperatura)
            print("Respuesta:", respuesta)
            LISTA_ERROR = ["No puedo responder a esa pregunta.", "No puedo responder a tu pregunta.", "No puedo responder a tu pregunta", ""]
            if respuesta or respuesta not in LISTA_ERROR:
                Conversacion.objects.create(
                    pregunta=pregunta, respuesta=respuesta, usuario=request.user, modelo=modelo, temperatura=temperatura)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

        return Response({"pregunta": pregunta, "respuesta": respuesta})

    def get(self, request):
        if request.user.is_authenticated:
            conversacion = Conversacion.objects.filter(
                usuario=request.user)
        else:
            # Si no hay usuario, se devuelve la lista general
            conversacion = Conversacion.objects.all()[:20]
        serializer = ConversacionSerializer(conversacion, many=True)
        return Response(serializer.data)


class ChatbotDetailView(APIView):
    serializer_class = ConversacionSerializer

    def get_authenticators(self):
        if self.action == 'post':
            return []
        return super().get_authenticators()

    def get(self, request, pk):
        try:
            conversacion = Conversacion.objects.get(
                pk=pk, user=request.user)
            serializer = Conversacion(conversacion)
            return Response(serializer.data)
        except ConversacionSerializer.DoesNotExist:
            return Response(
                {'error': 'Conversación no encontrada'},
                status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

