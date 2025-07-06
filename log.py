from colorama import init, Fore, Style
import sys
import os
import datetime


class Log:
    def __init__(self):
        init(autoreset=True)
        self.new_line = False
        self.last_output_type = ''
        
        # Log dosyası için dizin oluştur (programın çalıştığı dizininde)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(current_dir, 'logs')
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, mode=0o755)
            except Exception:
                # Eğer oluşturulamazsa geçici dizin kullan
                log_dir = '/tmp/gonullu_logs'
                if not os.path.exists(log_dir):
                    os.makedirs(log_dir, mode=0o755)
        
        # Log dosyası adı (tarih ile)
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = os.path.join(log_dir, f'gonullu_{timestamp}.log')
        
        # İlk log mesajı
        self._write_to_file(f"=== Gonullu Log Başlangıcı: {datetime.datetime.now()} ===")

    def _write_to_file(self, message):
        """Mesajı dosyaya yazar"""
        try:
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f'[{timestamp}] {message}\n')
        except Exception:
            pass  # Dosya yazma hatası olursa sessizce geç

    def error(self, message, continued=False):
        # burada hata mesajlarımızı yazdıracağız.
        log_message = f'[x] Hata: {message}'
        
        if continued is True:
            if self.last_output_type != 'error':
                self.blank_line()
            print(Fore.RED + '  ' + log_message + Style.RESET_ALL, end="\r")
            self.last_output_type = 'error'
            self.new_line = True
        else:
            if self.new_line is True:
                self.blank_line()
            print(Fore.RED + '  ' + log_message + Style.RESET_ALL)
            self.new_line = False
        
        # Dosyaya yaz
        self._write_to_file(log_message)

    def information(self, message, continued=False):
        # burada bilgi mesajlarımızı yazdıracağız.
        log_message = f'[*] Bilgi: {message}'
        
        if continued is True:
            if self.last_output_type != 'information':
                self.blank_line()
            print(Fore.LIGHTBLUE_EX + '  ' + log_message + Style.RESET_ALL, end="\r")
            self.last_output_type = 'information'
            self.new_line = True
        else:
            self.new_line = False
            print(Fore.LIGHTBLUE_EX + '  ' + log_message + Style.RESET_ALL)
        
        # Dosyaya yaz
        self._write_to_file(log_message)

    def success(self, message):
        # burada başarılı işlem mesajlarımızı yazdıracağız.
        log_message = f'[+] Başarılı: {message}'
        
        if self.new_line is True:
            self.blank_line()
        print(Fore.GREEN + '  ' + log_message + Style.RESET_ALL)
        
        # Dosyaya yaz
        self._write_to_file(log_message)

    def warning(self, message, continued=False):
        # burada uyarı mesajlarımız olacak.
        log_message = f'[!] Uyarı: {message}'
        
        if continued is True:
            if self.last_output_type != 'warning':
                self.blank_line()
            print(Fore.LIGHTBLUE_EX + '  ' + log_message + Style.RESET_ALL, end="\r")
            self.last_output_type = 'warning'
        else:
            if self.new_line is True:
                self.blank_line()
            print(Fore.YELLOW + '  ' + log_message + Style.RESET_ALL)
        
        # Dosyaya yaz
        self._write_to_file(log_message)

    @staticmethod
    def get_exit():
        sys.exit()

    def blank_line(self):
        self.new_line = False
        print('')
        # Dosyaya boş satır yazma
        self._write_to_file('')
