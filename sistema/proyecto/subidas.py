from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.files.uploadhandler import FileUploadHandler

LIMITE = 10 * 1024 * 1024


class SubidaLimitada(FileUploadHandler):
    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.memoria = BytesIO()
        self.excedido = False

    def receive_data_chunk(self, raw_data, start):
        if not self.excedido:
            if self.memoria.tell() + len(raw_data) > LIMITE:
                self.excedido = True
                self.memoria = BytesIO()
            else:
                self.memoria.write(raw_data)
        return None

    def file_complete(self, file_size):
        self.memoria.seek(0)
        return InMemoryUploadedFile(
            file=self.memoria,
            field_name=self.field_name,
            name=self.file_name,
            content_type=self.content_type,
            size=LIMITE + 1 if self.excedido else self.memoria.getbuffer().nbytes,
            charset=self.charset,
            content_type_extra=self.content_type_extra,
        )
