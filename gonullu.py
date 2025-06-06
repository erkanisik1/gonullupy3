#!/usr/bin/env python3
import argparse
import os
import signal
import sys
import traceback
import yaml
import getpass

from log import Log
from farm import Farm
from volunteer import Volunteer



def usage():
    print("""
Kullanim - Usage
Asagidaki satir, docker icindeki /etc/pisi/pisi.conf icinde bulunan
-j parametresini verecegimiz rakam ile degistirir.
\tsudo gonullu -j 24
Asagidaki satir, docker icin islemcinin %70'ini, fiziksel hafizanin
%25'ini  ayirir.
\tsudo gonullu --cpu=70 --memory=25
""")
    sys.exit()


def get_saved_email():
    config_file = os.path.join(os.path.dirname(__file__), 'config/mail_config.yml')
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
            if config and config.get('is_verified'):
                return config.get('email')
    return None


def main(log_main, volunteer_main, farm_main):
    while 1:
        response = farm_main.get_package()
        if (response == -1) or (response ==  -2):
            if response == -1:
                farm_main.wait(message='dir yeni paket bekleniyor.')
        else:
            volunteer_main.get_package_farm(response)
            while 1:
                if volunteer_main.check():
                    # container bulunamadı. İşlem bitti.
                    if farm_main.send_file(response['package'], response['binary_repo_dir']):
                        success = int(open('/tmp/gonullu/%s/%s.bitti' % (response['package'],
                                                                         response['package']), 'r').read())
                        farm_main.get('updaterunning?id=%s&state=%s' % (response['queue_id'], success), json=False)
                        volunteer_main.remove()
                        log_main.success(
                            message='derleme işlemi %s paketi için %s saniyede bitti.' % (response['package'],
                                                                                          farm_main.get_total_time())
                        )
                        log_main.blank_line()
                        farm_main.wait(reset=True)
                    break
                else:
                    # container bulundu. İşlem sürüyor.
                    farm_main.wait(message='den beri derleme işlemi %s paketi için devam ediyor.' % response['package'])


if __name__ == "__main__":
    log = Log()

    # Sinyal yönetimini ayarla
    def signal_handler(signum, frame):
        print("\nProgram sonlandırılıyor...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(description='This is pisilinux volunteer application')
    parser.add_argument('-k', '--kullanim', action="store_true", dest='usage', default=False)
    parser.add_argument('-m', '--memory', action='store', dest='memory_limit', default=50, type=int)
    parser.add_argument('-c', '--cpu', action='store', dest='cpu_set', default=1, type=int)
    parser.add_argument('-e', '--email', action='store', dest='email', default=None, type=str)
    parser.add_argument('-p', '--password', action='store', dest='password', default=None, type=str)
    parser.add_argument('-j', '--job', action='store', dest='job', default=5, type=int)

    args = parser.parse_args()

    if args.usage:
        usage()

    if os.getgid() != 0:
        log.error('Lütfen programı yönetici(sudo) olarak çalıştırınız.')
        log.get_exit()

    docker_socket_file = '/var/run/docker.sock'
    if not os.path.exists(docker_socket_file):
        log.error(message='Lütfen ilk önce docker servisini çalıştırınız!')
        log.get_exit()

    # Mail adresi kontrolü
    saved_email = get_saved_email()
    if not args.email and not saved_email:
        log.information('İlk kez çalıştırıyorsunuz. Lütfen mail adresinizi girin:')
        email = input('Mail adresi: ').strip()
       
        if not email:
            log.error('Mail adresi boş olamaz!')
            log.get_exit()
        args.email = email
       
    elif not args.email:
        args.email = saved_email
        log.information(f'Kayıtlı mail adresi kullanılıyor: {saved_email}')

    #print(args)

    #farm = Farm('https://ciftlik.pisilinux.org/ciftlik', args.email)
    farm = Farm('http://31.207.82.178/', args.email)
    volunteer = Volunteer(args)

    try:
        os.system("stty -echo")
        main(log, volunteer, farm)
    except SystemExit as e:
        # Program düzgün şekilde sonlandırıldı
        if e.code == 0:
            log.information("Program düzgün şekilde sonlandırıldı.")
        else:
            log.error(f"Program hata kodu {e.code} ile sonlandırıldı.")
    except Exception as e:
        log.error('Bilinmeyen bir hata ile karşılaşıldı: %s' % (traceback.format_exc()))
    finally:
        os.system("stty echo")
        sys.exit(0)
