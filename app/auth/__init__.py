"""Kimlik doğrulama paketi: JWT üretme/çözme (jwt_core) ve kullanıcı tablosu işlemleri (user_repository).
Parolalar scrypt ile hash'lenir; düz şifre hiçbir yerde saklanmaz.
İstek başına kullanıcı doğrulaması app/deps.py'de yapılır.
"""
