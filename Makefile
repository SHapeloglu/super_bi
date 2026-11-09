# Test hedefleri. Kullanım: make test
# Önce güvenlik testleri, sonra ortam değişkeni tanımlı entegrasyon testleri. Toplam 15 dk'yı aşmaz.
# Entegrasyon için DB'ler: docker compose -f docker-compose.test.yml up -d --wait

.PHONY: test

test:
	timeout 900 sh scripts/test.sh all
