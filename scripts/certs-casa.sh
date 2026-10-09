#!/bin/sh
# Certificado da casa (spec 002-pwa, R6): uma CA local + o certificado do edge
# assinado por ela, para o HTTPS pelo IP da casa ser confiável nos aparelhos
# que instalarem a CA (guia: docs/guia-certificado-casa.md).
#
#   ./scripts/certs-casa.sh [IP]      # IP padrão: 192.168.86.47
#
# - A CA (docker/certs/ca/sociman-ca.key/.crt) só é criada se ainda não existir.
#   Recriar a CA obriga a reinstalá-la em todos os aparelhos.
# - O certificado do servidor (docker/certs/localhost.pem/-key.pem) é sempre
#   reemitido: rodar de novo renova a validade ou troca o IP.
# - Tudo roda no container alpine/openssl como UID 1000 (sem sudo, sem
#   instalar nada no host). A chave da CA nunca sai de docker/certs/ca/
#   (gitignored) e nunca é impressa.
set -eu

IP="${1:-192.168.86.47}"
cd "$(dirname "$0")/.."

mkdir -p docker/certs/ca
# Se o edge subiu antes deste script, o Docker criou os pontos de montagem da CA
# pública como pastas vazias (de root). Pastas vazias saem com rmdir mesmo assim.
for f in docker/certs/ca/sociman-ca.crt docker/certs/ca/sociman-ca.cer; do
  if [ -d "$f" ]; then rmdir "$f"; fi
done

docker run --rm -i --user 1000:1000 --entrypoint /bin/sh \
  -e IP="$IP" \
  -v "$PWD/docker/certs:/certs" \
  alpine/openssl -s <<'EOF'
set -eu
umask 077
cd /certs

# (1) CA da casa, só se não existir
if [ ! -f ca/sociman-ca.key ]; then
  echo "[certs] criando a CA da casa"
  openssl req -x509 -newkey rsa:3072 -nodes -days 3650 -sha256 \
    -keyout ca/sociman-ca.key -out ca/sociman-ca.crt \
    -subj "/CN=SociMan CA da casa" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash"
  chmod 600 ca/sociman-ca.key
else
  echo "[certs] CA da casa já existe; mantida"
fi

# (2) certificado do servidor, assinado pela CA (arquivos temporários + mv
# para o nginx nunca ler um par pela metade)
cat > /tmp/servidor.ext <<EXT
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:${IP},DNS:localhost,IP:127.0.0.1
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid
EXT
openssl req -new -newkey rsa:2048 -nodes \
  -keyout localhost-key.pem.tmp -out /tmp/servidor.csr -subj "/CN=SociMan"
openssl x509 -req -in /tmp/servidor.csr -days 825 -sha256 \
  -CA ca/sociman-ca.crt -CAkey ca/sociman-ca.key \
  -CAserial ca/sociman-ca.srl -CAcreateserial \
  -extfile /tmp/servidor.ext -out localhost.pem.tmp
chmod 600 localhost-key.pem.tmp
chmod 644 localhost.pem.tmp
mv localhost-key.pem.tmp localhost-key.pem
mv localhost.pem.tmp localhost.pem
openssl verify -CAfile ca/sociman-ca.crt localhost.pem

# (3) CA em DER (.cer, para o Android); o .crt já é o PEM
openssl x509 -in ca/sociman-ca.crt -outform DER -out ca/sociman-ca.cer
chmod 644 ca/sociman-ca.crt ca/sociman-ca.cer

# (4) o que o dono precisa conferir
echo
echo "Impressão digital SHA-256 da CA (confira no aparelho ao instalar):"
openssl x509 -in ca/sociman-ca.crt -noout -fingerprint -sha256 | sed 's/^.*=/  /'
echo "Validade da CA:      $(openssl x509 -in ca/sociman-ca.crt -noout -enddate | cut -d= -f2)"
echo "Validade do servidor: $(openssl x509 -in localhost.pem -noout -enddate | cut -d= -f2)"
echo "Nomes do servidor:    IP:${IP}, DNS:localhost, IP:127.0.0.1"
EOF

# (5) o edge relê os certificados
docker compose restart edge
