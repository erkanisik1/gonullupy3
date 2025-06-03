#!/bin/bash

# Gerekli servisleri başlat
service dbus start

# Temel sistem güncellemeleri
pisi cp
update-ca-certificates

# Pisi depolarını ekle
pisi ar pisiBeta https://beta.pisilinux.org/pisi-index.xml.xz
pisi ar core --ignore-check https://github.com/pisilinux/core/raw/master/pisi-index.xml.xz
pisi ar main --ignore-check https://github.com/pisilinux/main/raw/master/pisi-index.xml.xz --at 2

# Gerekli paketleri yükle
pisi it --ignore-safety --ignore-dependency \
    autoconf autogen automake binutils bison flex gawk gc gcc \
    gnuconfig guile libmpc libsigsegv libtool-ltdl libtool lzo \
    m4 make mpfr nasm pkgconfig yacc glibc-devel isl ${KERNEL_REQUIREMENT}

# Sistem güncellemesi
pisi ur

# Pisi yapılandırmasını güncelle
sed -i "s/-j5/-j${JOB_COUNT}/g" /etc/pisi/pisi.conf
sed -i 's/build_host = localhost/build_host=farmV5/g' /etc/pisi/pisi.conf

# Derleme dizinine git
cd /root

# Paketi derle
pisi bi --ignore-safety${SANDBOX_OPTION} -y ${PACKAGE_NAME} \
    1>/root/${PACKAGE_NAME}/${PACKAGE_NAME}-${BRANCH}-${COMMIT_ID}.log \
    2>/root/${PACKAGE_NAME}/${PACKAGE_NAME}-${BRANCH}-${COMMIT_ID}.err

# Derleme durumunu kaydet
STAT=$?

# Oluşan pisi dosyalarını taşı
for pisi_file in $(ls *.pisi 2>/dev/null); do
    mv "$pisi_file" "/root/${PACKAGE_NAME}/${PACKAGE_NAME}-${BRANCH}-${pisi_file}"
done

# İşlem durumunu kaydet
echo $STAT > "/root/${PACKAGE_NAME}/${PACKAGE_NAME}.bitti"
