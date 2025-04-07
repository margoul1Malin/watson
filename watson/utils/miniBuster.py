import sys
import requests
import random
import time
from colorama import init, Fore, Style
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import urllib3
from fake_useragent import UserAgent
import os
from datetime import datetime
import socket
import dns.resolver

# Désactiver les avertissements SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Initialiser colorama
init()

# Variables globales
username = ""
url_list_file = ""
speed_option = "fast"  # "fast" ou "slow" par défaut
# Créer des locks globaux pour l'affichage et l'écriture dans le fichier
print_lock = Lock()
file_lock = Lock()

# Vérifier les arguments si le script est exécuté directement
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python miniBuster.py <url_list_file> <username> [speed]")
        print("Example: python miniBuster.py urls.txt john fast")
        sys.exit(1)

    url_list_file = sys.argv[1]
    username = sys.argv[2]
    
    # Vérifier s'il y a une option de vitesse spécifiée
    if len(sys.argv) > 3 and sys.argv[3] in ["fast", "slow"]:
        speed_option = sys.argv[3]
    else:
        speed_option = "fast"  # Valeur par défaut

# Vérifier si le fichier d'URLs existe
def check_url_file():
    """Vérifie si le fichier d'URLs existe et est lisible"""
    if not os.path.exists(url_list_file):
        print(f"{Fore.RED}Error: File {url_list_file} not found{Style.RESET_ALL}")
        # Au lieu de terminer l'exécution, lever une exception
        raise FileNotFoundError(f"Le fichier {url_list_file} n'existe pas")
    
    # Vérifier si le fichier est lisible
    if not os.access(url_list_file, os.R_OK):
        print(f"{Fore.RED}Error: File {url_list_file} is not readable{Style.RESET_ALL}")
        raise PermissionError(f"Le fichier {url_list_file} n'est pas lisible")
    
    return True

# Initialiser UserAgent
ua = UserAgent()

# Liste des headers possibles avec plus de variations
HEADERS = [
    {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'DNT': '1'
    }
]

def update_paths_with_username(current_username):
    """Mets à jour les chemins avec le nom d'utilisateur actuel"""
    paths = [
        "/users/{0}",
        "/user/{0}",
        "/profile/{0}",
        "/account/{0}",
        "/settings/{0}",
        "/dashboard/{0}",
        "/people/{0}",
        "/@{0}",
        "/users/@{0}",
        "/user/@{0}",
        "/profile/@{0}",
        "/account/@{0}",
        "/settings/@{0}",
        "/dashboard/@{0}",
        "/people/@{0}",
        "/{0}",
        "/u/{0}",
        "/p/{0}",
        "/a/{0}",
        "/s/{0}",
        "/d/{0}",
        "/member/{0}",
        "/members/{0}",
        "/profile.php?user={0}",
        "/user.php?name={0}",
        "/profile.php?username={0}",
        "/user.php?username={0}",
        "/profile.php?id={0}",
        "/user.php?id={0}",
        "/profile/{0}/",
        "/user/{0}/",
        "/account/{0}/",
        "/settings/{0}/",
        "/dashboard/{0}/",
        "/people/{0}/",
        "/@{0}/",
        "/users/@{0}/",
        "/user/@{0}/",
        "/profile/@{0}/",
        "/account/@{0}/",
        "/settings/@{0}/",
        "/dashboard/@{0}/",
        "/people/@{0}/",
        "/{0}/",
        "/u/{0}/",
        "/p/{0}/",
        "/a/{0}/",
        "/s/{0}/",
        "/d/{0}/",
        "/member/{0}/",
        "/members/{0}/",
        "/admin/{0}",
        "/admin/@{0}",
        "/admin/{0}/",
        "/admin/@{0}/",
        "/mod/{0}",
        "/mod/@{0}",
        "/mod/{0}/",
        "/mod/@{0}/",
        "/staff/{0}",
        "/staff/@{0}",
        "/staff/{0}/",
        "/staff/@{0}/",
        "/view/{0}",
        "/view/@{0}",
        "/view/{0}/",
        "/view/@{0}/",
        "/show/{0}",
        "/show/@{0}",
        "/show/{0}/",
        "/show/@{0}/",
        "/public/{0}",
        "/public/@{0}",
        "/public/{0}/",
        "/public/@{0}/",
        "/private/{0}",
        "/private/@{0}",
        "/private/{0}/",
        "/private/@{0}/",
        "/home/{0}",
        "/home/@{0}",
        "/home/{0}/",
        "/home/@{0}/",
        "/page/{0}",
        "/page/@{0}",
        "/page/{0}/",
        "/page/@{0}/",
        "/info/{0}",
        "/info/@{0}",
        "/info/{0}/",
        "/info/@{0}/",
        "/details/{0}",
        "/details/@{0}",
        "/details/{0}/",
        "/details/@{0}/",
        "/about/{0}",
        "/about/@{0}",
        "/about/{0}/",
        "/about/@{0}/",
        "/me/{0}",
        "/me/@{0}",
        "/me/{0}/",
        "/me/@{0}/"
    ]
    return [path.format(current_username) for path in paths]

def check_subdomain_support(domain):
    """Vérifie si le domaine supporte les sous-domaines"""
    try:
        # Vérifier si le domaine a des enregistrements NS
        resolver = dns.resolver.Resolver()
        resolver.timeout = 2
        resolver.lifetime = 2
        resolver.resolve(domain, 'NS')
        return True
    except:
        return False

def get_random_delay(option=None):
    """Retourne un délai aléatoire en fonction de l'option de vitesse"""
    option = option or speed_option  # Utiliser l'argument ou la variable globale
    
    if option == "fast":
        return random.uniform(0.1, 0.3)
    elif option == "slow":
        return random.uniform(0.5, 1.0)
    else:
        return random.uniform(0.1, 1.0)

def log_result(url, status_code, path, log_file):
    """Écrit le résultat dans le fichier de log"""
    with file_lock:
        with open(log_file, 'a') as f:
            f.write(f"{url}{path} - Status: {status_code}\n")

def test_path(url, path, headers, log_file):
    """Teste un chemin spécifique avec un header aléatoire"""
    try:
        # Format standard : site.com/username
        full_url = f"{url.rstrip('/')}{path}"
        
        # Ajouter un délai aléatoire avant la requête
        time.sleep(get_random_delay())
        
        # Ajouter des paramètres aléatoires pour éviter le cache
        random_params = {
            'v': str(random.randint(1, 1000)),
            't': str(int(time.time())),
            'r': ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=5))
        }
        
        response = requests.get(
            full_url,
            headers=headers,
            params=random_params,
            timeout=10,
            allow_redirects=True,
            verify=False
        )
        
        # Loguer tous les résultats
        log_result(url, response.status_code, path, log_file)
        
        # Afficher uniquement les résultats intéressants (pas les 404 et 403)
        with print_lock:
            if response.status_code == 200:
                print(f"{Fore.GREEN}[+] {full_url} - Status: {Fore.YELLOW}{Style.BRIGHT}{response.status_code}{Style.RESET_ALL}")
            elif response.status_code not in [404, 403]:
                print(f"{Fore.BLUE}[?] {full_url} - Status: {Fore.YELLOW}{Style.BRIGHT}{response.status_code}{Style.RESET_ALL}")
        
        # Vérifier si le domaine supporte les sous-domaines
        domain = url.split('://')[1].split('/')[0]
        if check_subdomain_support(domain):
            # Format alternatif : username.site.com
            subdomain_url = f"{url.split('://')[0]}://{username}.{domain}"
            
            # Ajouter un délai aléatoire avant la requête
            time.sleep(get_random_delay())
            
            try:
                response_sub = requests.get(
                    subdomain_url,
                    headers=headers,
                    params=random_params,
                    timeout=10,
                    allow_redirects=True,
                    verify=False
                )
                
                # Loguer tous les résultats
                log_result(subdomain_url, response_sub.status_code, '', log_file)
                
                # Afficher uniquement les résultats intéressants
                with print_lock:
                    if response_sub.status_code == 200:
                        print(f"{Fore.GREEN}[+] {subdomain_url} - Status: {Fore.YELLOW}{Style.BRIGHT}{response_sub.status_code}{Style.RESET_ALL}")
                    elif response_sub.status_code not in [404, 403]:
                        print(f"{Fore.BLUE}[?] {subdomain_url} - Status: {Fore.YELLOW}{Style.BRIGHT}{response_sub.status_code}{Style.RESET_ALL}")
            except requests.exceptions.ConnectionError as e:
                # Ne pas afficher les erreurs de résolution de nom
                if "NameResolutionError" not in str(e):
                    with print_lock:
                        print(f"{Fore.RED}[X] {subdomain_url} - Error: {Fore.YELLOW}{Style.BRIGHT}{str(e)}{Style.RESET_ALL}")
                    with file_lock:
                        with open(log_file, 'a') as f:
                            f.write(f"{subdomain_url} - Error: {str(e)}\n")
            
        return response.status_code
    except Exception as e:
        if "NameResolutionError" not in str(e):
            with print_lock:
                print(f"{Fore.RED}[X] {full_url} - Error: {Fore.YELLOW}{Style.BRIGHT}{str(e)}{Style.RESET_ALL}")
            with file_lock:
                with open(log_file, 'a') as f:
                    f.write(f"{full_url} - Error: {str(e)}\n")
        return None

def main(url_file=None, user=None, speed=None):
    """
    Fonction principale pour exécuter le miniBuster
    
    Args:
        url_file (str): Chemin vers le fichier contenant les URLs
        user (str): Nom d'utilisateur à tester
        speed (str): Vitesse de recherche ('fast' ou 'slow')
    """
    global username, url_list_file, speed_option, POSSIBILITIES
    
    # Utiliser les paramètres fournis ou les variables globales
    username = user or username
    url_list_file = url_file or url_list_file
    speed_option = speed or speed_option
    
    # Vérifier le fichier d'URLs
    check_url_file()
    
    # Mettre à jour la liste des chemins possibles avec le username actuel
    POSSIBILITIES = update_paths_with_username(username)
    
    # Créer le dossier logs s'il n'existe pas
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Créer le fichier de log avec timestamp
    log_file = f"logs/buster_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    # Lire la liste des URLs
    with open(url_list_file, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
    
    print(f"\n{Fore.CYAN}[*] Testing paths for {username} on multiple URLs{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[*] Mode de vitesse: {speed_option}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[*] Log file: {log_file}{Style.RESET_ALL}\n")
    
    # Ajuster le nombre de workers en fonction de la vitesse
    max_workers = 5 if speed_option == "slow" else 10
    
    # Exécuter les tests
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for url in urls:
            print(f"\n{Fore.YELLOW}[*] Testing URL: {url}{Style.RESET_ALL}")
            for path in POSSIBILITIES:
                headers = random.choice(HEADERS)
                future = executor.submit(test_path, url, path, headers, log_file)
                futures.append(future)
        
        for future in futures:
            future.result()
    
    print(f"\n{Fore.CYAN}[*] Test terminé. Résultats enregistrés dans {log_file}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()