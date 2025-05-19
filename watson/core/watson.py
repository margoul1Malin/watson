import requests
from bs4 import BeautifulSoup
import cloudscraper
from colorama import init, Fore, Style
import json
import threading
import random
import time
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
import argparse
import os
import sys
from googleapiclient.discovery import build
import importlib.resources
from pathlib import Path

# Obtenir les chemins des ressources de manière fiable
def get_resource_path(relative_path):
    """Obtient le chemin absolu d'un fichier de ressources, que ce soit en développement ou installé via pip"""
    try:
        # D'abord essayer de localiser le package de base
        package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Construire le chemin absolu
        absolute_path = os.path.join(package_root, relative_path)
        
        # Si le chemin n'existe pas, chercher dans le répertoire parent (pour le développement)
        if not os.path.exists(absolute_path):
            parent_dir = os.path.dirname(package_root)
            absolute_path = os.path.join(parent_dir, relative_path)
            
        return absolute_path
    except Exception as e:
        print(f"{Fore.YELLOW}Attention: Problème lors de la recherche du chemin des ressources: {str(e)}.{Style.RESET_ALL}")
        # Retour au chemin relatif simple en dernier recours
        return relative_path

# Vérifier que le répertoire ressources existe
resource_dir = get_resource_path('ressources')
if not os.path.exists(resource_dir):
    os.makedirs(resource_dir)
    print(f"{Fore.YELLOW}Répertoire 'ressources' créé.{Style.RESET_ALL}")

api_file_path = get_resource_path('ressources/apikeys.json')

# Initialiser la variable yt_apikey avec une valeur par défaut
yt_apikey = None

# Charger les clés API si le fichier existe
if os.path.exists(api_file_path):
    try:
        with open(api_file_path, "r") as file:
            api_data = json.load(file)
        yt_apikey = api_data.get("yt_apikey")
    except Exception as e:
        print(f"{Fore.YELLOW}Attention: Impossible de charger le fichier de clés API: {str(e)}. Certaines fonctionnalités peuvent être indisponibles.{Style.RESET_ALL}")


def check_twitch_username(username):
    """
    Vérifie si un nom d'utilisateur existe sur Twitch
    en analysant le contenu de la page de profil.
    """
    url = f"https://www.twitch.tv/{username}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    
    try:
        response = requests.get(url, headers=headers, allow_redirects=True)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Compter les occurrences du mot "error" dans la réponse
        error_count = response.text.lower().count("error")
        
        # Pour Twitch, il faut analyser d'autres indicateurs
        page_title = soup.title.text if soup.title else ""
        
        # Si l'URL finale contient des paramètres de redirection, c'est probablement une page d'erreur
        if "?error=true" in response.url or "error=404" in response.url:
            return {
                "platform": "Twitch",
                "exists": False,
                "url": url,
                "message": "Utilisateur non trouvé (détection par URL d'erreur)"
            }
        
        # Compter les occurrences de phrases qui indiquent un profil inexistant
        time_machine_count = response.text.lower().count("time machine") + response.text.lower().count("machine à voyager")
        not_found_count = response.text.lower().count("not found") + response.text.lower().count("not available")
        
        if time_machine_count > 0 or not_found_count > 3:
            return {
                "platform": "Twitch",
                "exists": False,
                "url": url,
                "message": "Utilisateur non trouvé (détection par phrases d'erreur spécifiques)"
            }
        
        # Termes qui indiquent un profil inexistant
        not_found_phrases = [
            "Page not found",
            "error-page",
            "Désolé.  À moins que vous ayez une machine à voyager dans le temps, ce contenu n'est pas disponible.",
            "Sorry. Unless you've got a time machine, that content is unavailable."
        ]
        
        for phrase in not_found_phrases:
            if phrase in response.text:
                return {
                    "platform": "Twitch",
                    "exists": False,
                    "url": url,
                    "message": "Utilisateur non trouvé"
                }
        
        # Rechercher des indicateurs positifs spécifiques d'existence
        
        # 1. Vérification du meta title
        user_meta = soup.find("meta", property="og:title")
        if user_meta and username.lower() in user_meta.get("content", "").lower():
            return {
                "platform": "Twitch",
                "exists": True,
                "url": url,
                "message": "Profil trouvé (détection par méta titre)"
            }
            
        # 2. Rechercher des patterns spécifiques qui indiquent un profil existant
        positive_indicators = [
            f"\"channelURL\":\"https://www.twitch.tv/{username.lower()}\"",
            f"\"login\":\"{username.lower()}\"",
            f"\"displayName\":\"{username}\"",
            "isLiveBroadcast",
            f"\"username\":\"{username.lower()}\""
        ]
        
        for indicator in positive_indicators:
            if indicator in response.text.lower():
                return {
                    "platform": "Twitch",
                    "exists": True,
                    "url": url,
                    "message": f"Profil trouvé (détection par indicateur: {indicator.split(':')[0]})"
                }
            
        # 3. Chercher des éléments HTML spécifiques aux profils existants
        profile_elements = soup.find_all("h1", {"data-a-target": "channel-header-info"})
        follow_button = soup.find("button", string=lambda s: s and "Follow" in s)
            
        if profile_elements or follow_button:
            return {
                "platform": "Twitch",
                "exists": True,
                "url": url,
                "message": "Profil trouvé (détection par éléments HTML)"
            }
        
        # 4. Vérifier les scripts pour les données utilisateur
        scripts = soup.find_all("script")
        for script in scripts:
            script_text = script.string if script.string else ""
            if f"\"login\":\"{username.lower()}\"" in script_text:
                return {
                    "platform": "Twitch",
                    "exists": True,
                    "url": url,
                    "message": "Profil trouvé (détection par données script)"
                }
        
        # Pour les noms d'utilisateur vraiment aléatoires, il est improbable qu'ils existent.
        # Si le nom d'utilisateur est très long et semble aléatoire (pas dans le titre/meta),
        # on suppose qu'il n'existe pas, malgré le contenu de réponse substantiel.
        import re
        if len(username) > 15 and re.match(r'^[a-zA-Z0-9]+$', username) and len(response.text) > 100000:
            return {
                "platform": "Twitch",
                "exists": False,
                "url": url,
                "message": "Utilisateur probablement inexistant (nom long et aléatoire)"
            }
            
        return {
            "platform": "Twitch", 
            "exists": None,
            "url": url,
            "message": "Impossible de déterminer"
        }
        
    except Exception as e:
        return {
            "platform": "Twitch",
            "exists": None,
            "url": url,
            "error": str(e)
        }


def check_instagram_username(username):
    """
    Vérifie si un nom d'utilisateur existe sur Instagram
    en analysant le contenu de la page de profil.
    """
    import requests
    from bs4 import BeautifulSoup
    import json
    import re
    
    url = f"https://www.instagram.com/{username}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    
    try:
        response = requests.get(url, headers=headers, allow_redirects=True)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Compter les occurrences du mot "error" dans la réponse
        error_count = response.text.lower().count("error")
        
        # Vérifier si l'URL contient des paramètres d'erreur (après redirection)
        if "error" in response.url or "challenge" in response.url:
            return {
                "platform": "Instagram",
                "exists": False,
                "url": url,
                "message": "Profil non trouvé (détection par URL d'erreur)"
            }
        
        # Imprimer les premières lignes pour débogage
        
        # Compter le nombre de "Page Not Found" ou "Sorry"
        not_found_count = response.text.count("Page Not Found") + response.text.count("Sorry, this page")
        
        # Si plusieurs occurrences de "Page Not Found", le profil n'existe probablement pas
        if not_found_count > 1:
            return {
                "platform": "Instagram",
                "exists": False,
                "url": url,
                "message": "Profil non trouvé (détection par phrases 'not found')"
            }
        
        # 1. Vérifier les phrases d'erreur spécifiques à Instagram
        not_found_phrases = [
            "Page Not Found",
            "Page Indisponible",
            "content isn't available",
            "Sorry, this page isn't available",
            "Profile n'est pas disponible",
            "The link you followed may be broken",
            "Désolé, cette page n'est pas disponible"
        ]
        
        for phrase in not_found_phrases:
            if phrase in response.text:
                return {
                    "platform": "Instagram",
                    "exists": False,
                    "url": url,
                    "message": "Profil non trouvé"
                }
         
        # Recherche de patterns spécifiques aux profils existants
        profile_indicators = [
            f"\"username\":\"{username}\"",
            f"\"user\":{{\"username\":\"{username}\"",
            "profile_pic_url",
            "edge_followed_by",
            "edge_follow"
        ]
        
        for indicator in profile_indicators:
            if indicator in response.text:
                return {
                    "platform": "Instagram",
                    "exists": True,
                    "url": url,
                    "message": f"Profil trouvé (détection par indicateur: {indicator.split(':')[0]})"
                }
            
        # 2. Chercher des données de profil dans les balises script
        profile_data = None
        scripts = soup.find_all("script", type="text/javascript")
        for script in scripts:
            if script.string and "window._sharedData" in script.string:
                json_str = script.string.replace("window._sharedData = ", "").rstrip(";")
                try:
                    data = json.loads(json_str)
                    profile_data = data.get("entry_data", {}).get("ProfilePage", [{}])[0].get("graphql", {}).get("user")
                    break
                except:
                    pass
                    
        if profile_data:
            return {
                "platform": "Instagram",
                "exists": True,
                "url": url,
                "username": profile_data.get("username"),
                "followers": profile_data.get("edge_followed_by", {}).get("count", 0),
                "message": "Profil trouvé"
            }
        
        # Vérifier les noms d'utilisateur longs et aléatoires
        import re
        if len(username) > 15 and re.match(r'^[a-zA-Z0-9]+$', username):
            return {
                "platform": "Instagram",
                "exists": False,
                "url": url,
                "message": "Utilisateur probablement inexistant (nom long et aléatoire)"
            }
            
        # 3. Rechercher les mots-clés spécifiques
        meta_desc = soup.find("meta", property="og:description")
        if meta_desc and username.lower() in meta_desc.get("content", "").lower():
            return {
                "platform": "Instagram",
                "exists": True,
                "url": url,
                "message": "Profil trouvé (détection par meta description)"
            }
        
        # 4. Vérifier le titre de la page
        page_title = soup.title.text if soup.title else ""
        
        # Si la page contient "Instagram" mais pas d'indicateurs d'erreur, 
        # et que le nom d'utilisateur n'est pas très long, supposer que le profil existe
        if "Instagram" in page_title and not_found_count == 0 and len(username) < 10:
            return {
                "platform": "Instagram",
                "exists": True,
                "url": url,
                "message": "Profil probablement trouvé (détection par analyse de page)"
            }
        
        return {
            "platform": "Instagram",
            "exists": None,
            "url": url,
            "message": "Impossible de déterminer",
            "html_sample": response.text[:500]  # Échantillon pour analyse
        }
        
    except Exception as e:
        return {
            "platform": "Instagram",
            "exists": None,
            "url": url,
            "error": str(e)
        }

def check_facebook_username(username):
    """
    Vérifie si un nom d'utilisateur existe sur Facebook
    en analysant le contenu de la page de profil.
    """
    import requests
    from bs4 import BeautifulSoup
    import re
    
    url = f"https://www.facebook.com/{username}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
    }
    
    try:
        # Essayer une approche différente pour Facebook qui a une protection anti-scraping forte
        response = requests.get(url, headers=headers, allow_redirects=True)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Analyser l'URL finale après redirection
        
        # Extraire tout le texte visible de la page
        visible_text = ' '.join(soup.stripped_strings)
        
        # Facebook - Vérifier le titre de la page
        page_title = soup.title.text if soup.title else ""
        
        # Phrases qui indiquent clairement qu'un profil n'existe pas
        clear_not_found_phrases = [
            "This page isn't available",
            "The link you followed may have expired",
            "Page non trouvée",
            "Cette page n'existe pas",
            "We couldn't find anything",
            "Nous n'avons rien trouvé"
        ]
        
        for phrase in clear_not_found_phrases:
            if phrase in response.text:
                return {
                    "platform": "Facebook",
                    "exists": False,
                    "url": url,
                    "message": f"Profil non trouvé (phrase: '{phrase}')"
                }
        
        # Si on est redirigé vers une page de login ou checkpoint, c'est généralement
        # un signe que le profil existe mais nécessite une authentification
        if "login" in response.url or "checkpoint" in response.url:
            # Pour les noms d'utilisateur courts (plus susceptibles d'exister)
            if len(username) <= 15:
                return {
                    "platform": "Facebook",
                    "exists": True,
                    "url": url,
                    "message": "Profil probablement existant (redirection vers login)"
                }
        
        # Si le titre contient simplement "Error" mais qu'on n'a pas trouvé de phrases
        # claires indiquant que le profil n'existe pas, c'est probablement une protection anti-scraping
        if "Error" in page_title and not any(phrase in response.text for phrase in clear_not_found_phrases):
            # Pour les noms d'utilisateur qui semblent réels (pas trop longs ni aléatoires)
            if len(username) <= 15 and not re.match(r'^[a-zA-Z0-9]{15,}$', username):
                return {
                    "platform": "Facebook",
                    "exists": True,
                    "url": url,
                    "message": "Profil probablement existant (protection anti-scraping)"
                }
        
        # Pour les noms très longs et aléatoires, supposer que le profil n'existe pas
        if len(username) > 15 and re.match(r'^[a-zA-Z0-9]+$', username):
            return {
                "platform": "Facebook",
                "exists": False,
                "url": url,
                "message": "Profil probablement inexistant (nom long et aléatoire)"
            }
        
        # Si on arrive ici, c'est qu'on n'est pas sûr
        return {
            "platform": "Facebook",
            "exists": None,
            "url": url,
            "message": "Impossible de déterminer avec certitude",
            "html_sample": response.text[:500]  # Échantillon pour analyse
        }
        
    except Exception as e:
        return {
            "platform": "Facebook",
            "exists": None,
            "url": url,
            "error": str(e)
        }
    
def check_tryhackme_username(username):
    url = f"https://tryhackme.com/api/user/exist/{username}"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("success") == True:
            return {
                    "platform": "tryhackme",
                    "exists": True,
                    "url": url,
                    "message": "Username available"
                }
        else:
            return {
                    "platform": "tryhackme",
                    "exists": False,
                    "url": url,
                    "message": "Username not available"
                }
    else:
        return {
                    "platform": "tryhackme",
                    "exists": None,
                    "url": url,
                    "message": "Could not reach TryHackMe API"
                }
    

def check_discord_username(username):
    url = f"https://discord.com/api/v9/unique-username/username-attempt-unauthed"
    response = requests.post(url, json={"username": username})
    if response.status_code == 200:
        data = response.json()
        if "taken" in data:
            if data["taken"]:
                return {
                    "platform": "discord",
                    "exists": True,
                    "url": url,
                    "message": "Username taken"
                }
            else:
                return {
                    "platform": "discord",
                    "exists": False,
                    "url": url,
                    "message": "Username not taken"
                }
        else:
            return {
                    "platform": "discord",
                    "exists": None,
                    "url": url,
                    "message": "Could not reach Discord API"
                }
    else:
        return {
            "platform": "discord",
            "exists": None,
            "url": url,
            "message": f"Erreur {response.status_code} :"
        }

def check_imginn_username(username):
    url = f"https://imginn.com/{username}"
    response = requests.get(url)
    scraper = cloudscraper.create_scraper()

# Envoyer la requête GET avec les bons headers
    response = scraper.get(url)

    if "Page Not Found" in response.text:
        return {
            "platform": "imginn",
            "exists": False,
            "url": url,
            "message": "Username not available"
        }
    else:
        return {
            "platform": "imginn",
            "exists": True,
            "url": url,
            "message": "Username available"
        }

def check_medium_username(username):
    url = f"https://medium.com/@{username}"
    response = requests.get(url)
    if "PAGE NOT FOUND" in response.text:
        return {
            "platform": "medium",
            "exists": False,
            "url": url,
            "message": "Username not available"
        }
    else:
        return {
            "platform": "medium",
            "exists": True,
            "url": url,
            "message": "Username available"
        }

def check_tiktok_username(username):
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
    }
    url = "https://www.tiktok.com/@{}"
    response = requests.get(url.format(username), headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    if f'"uniqueId":"{username}"' in soup.prettify():
        return {
            "platform": "tiktok",
            "exists": True,
            "url": url,
            "message": "Username available"
        }
    else:
        return {
            "platform": "tiktok",
            "exists": False,
            "url": url,
            "message": "Username not available"
        }

def check_cracked_username(username):
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
    }

    url = "https://www.cracked.com/members/{}/"
    response = requests.get(url.format(username), headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    if not f"| Cracked.com - America's Only Humor Site | Cracked.com" in soup.prettify():
        return {
            "platform": "cracked",
            "exists": False,
            "url": url,
            "message": "Username not available"
        }
    else:
        return {
            "platform": "cracked",
            "exists": True,
            "url": url,
            "message": "Username available"
        }

def check_reddit_username(username):
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
    }
    url = "https://www.reddit.com/user/{}"
    response = requests.get(url.format(username), headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    if "<shreddit-redirect" in soup.prettify():
        return {
            "platform": "reddit",
            "exists": True,
            "url": url,
            "message": "Username available"
        }
    else:
        return {
            "platform": "reddit",
            "exists": False,
            "url": url,
            "message": "Username not available"
        }
    
def check_pinterest_username(username):
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
    }

    pattern = 'data-lazy-component=""'

    url = "https://www.pinterest.com/{}"
    response = requests.get(url.format(f"{username}"), headers=headers)
    
    soup = BeautifulSoup(response.text, "html.parser")
    count = soup.prettify().count(pattern)

    if count > 5:
        return {
            "platform": "pinterest",
            "exists": True,
            "url": url,
            "message": "Username available"
        }
    else:
        return {
            "platform": "pinterest",
            "exists": False,
            "url": url,
            "message": "Username not available"
        }
    
def check_gravatar_username(username):
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
    }
    url = "https://gravatar.com/{}"
    response = requests.get(url.format(f"{username}"), headers=headers)

    if "Gravatar - Globally Recognized Avatars (votre avatar universel)" in response.text:
        return {
            "platform": "gravatar",
            "exists": False,
            "url": url,
            "message": "Username not available"
        }
    else:
        return {
            "platform": "gravatar",
            "exists": True,
            "url": url,
            "message": "Username available"
        }
        
def check_hackenproof_username(username):
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
    }

    url = "https://hackenproof.com/hackers/{}"
    response = requests.get(url.format(f"{username}"), headers=headers)

    if not "| HackenProof" in response.text:
        return {
            "platform": "hackenproof",
            "exists": False,
            "url": url,
            "message": "Username not available"
        }
    else:
        return {
            "platform": "hackenproof",
            "exists": True,
            "url": url,
            "message": "Username available"
        }
    
def check_imginn_username(username):
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0"
    }
    
    pattern = '<link rel="canonical"'
    url = "https://imginn.com/{}"
    response = requests.get(url.format(f"{username}"), headers=headers)

    if pattern in response.text:
        return {
            "platform": "imginn",
            "exists": True,
            "url": url,
            "message": "Username available"
        }
    else:
        return {
            "platform": "imginn",
            "exists": False,
            "url": url,
            "message": "Username not available"
        }
    
def check_hackerrank_username(username):
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"    
    }
    
    pattern = 'function set_manifest(manifest)'
    url = "https://hackerrank.com/{}"
    response = requests.get(url.format(f"{username}"), headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    
    if pattern in soup.prettify():
        return {
            "platform": "hackerrank",
            "exists": False, 
            "url": url,
            "message": "Username unavailable"
        }
    else:
        return {
            "platform": "hackerrank",
            "exists": True,
            "url": url,
            "message": "Username available"
        }

def check_hackerearth_username(username):
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br", 
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"    
    }
    
    pattern = 'Developer Profile on HackerEarth.'
    url = "https://www.hackerearth.com/{}"
    response = requests.get(url.format(f"{username}"), headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")  

    if pattern in soup.prettify():
        return {
            "platform": "hackerearth",
            "exists": True,
            "url": url,
            "message": "Username available"
        }
    else:
        return {
            "platform": "hackerearth",
            "exists": False,    
            "url": url,
            "message": "Username not available"
        }

def check_wordpress_username(username):
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
    }
    
    url = "https://{}.wordpress.com/"
    start_time = time.time()  # Démarrer le chronomètre

    response = requests.get(url.format(username), headers=headers)
    
    elapsed_time = time.time() - start_time  # Calculer le temps écoulé
    # Si le temps de réponse est supérieur à 0.15s, considérer que l'utilisateur n'existe pas
    if elapsed_time > 0.15:
        return {
            "platform": "wordpress",
            "exists": False,
            "url": url,
            "message": "Username not available"
        }
    else:
        return {
            "platform": "wordpress",
            "exists": True,
            "url": url,
            "message": "Username available"
        }

def check_youtube_username(username):
    if not yt_apikey:
        return {
            "platform": "youtube",
            "exists": None,
            "url": "youtube.com/@{}",
            "message": "API key not configured. Use --api-config YOUTUBE your_api_key to configure it."
        }
        
    youtube = build('youtube', 'v3', developerKey=yt_apikey)
    try:
        # Essayer d'abord avec forUsername (identifiant historique)
        request = youtube.channels().list(
            part="snippet,contentDetails,statistics",
            forUsername=username
        )
        response = request.execute()

        # Si aucun résultat, essayer avec le format "@username" (identifiant plus récent)
        if not response.get('items', []):
            handle_request = youtube.search().list(
                part="snippet",
                q=f"@{username}",
                type="channel",
                maxResults=5
            )
            handle_response = handle_request.execute()
            
            # Vérifier si un canal correspondant est trouvé dans les résultats de recherche
            channel_id = None
            for item in handle_response.get('items', []):
                if item['snippet']['channelTitle'].lower() == username.lower() or f"@{username.lower()}" in item['snippet']['channelTitle'].lower():
                    channel_id = item['snippet']['channelId']
                    break
            
            # Si un canal correspondant est trouvé, obtenir ses détails
            if channel_id:
                channel_request = youtube.channels().list(
                    part="snippet,contentDetails,statistics",
                    id=channel_id
                )
                response = channel_request.execute()

        # Vérifier si un élément est retourné (si la chaîne existe)
        if response.get('items', []):
            channel = response['items'][0]
            channel_title = channel['snippet']['title']
            subscriber_count = channel['statistics'].get('subscriberCount', 'Hidden')
            video_count = channel['statistics'].get('videoCount', '0')
            view_count = channel['statistics'].get('viewCount', '0')
            
            # Formater les nombres pour une meilleure lisibilité
            try:
                if subscriber_count != 'Hidden':
                    subscriber_count = f"{int(subscriber_count):,}".replace(',', ' ')
                view_count = f"{int(view_count):,}".replace(',', ' ')
                video_count = f"{int(video_count):,}".replace(',', ' ')
            except:
                pass  # Si le formatage échoue, utiliser les valeurs non formatées
            
            creation_date = channel['snippet'].get('publishedAt', '').split('T')[0]
            description = channel['snippet'].get('description', '')
            
            # Tronquer la description si elle est trop longue
            if description and len(description) > 100:
                description = description[:97] + "..."
                
            message = f"{channel_title} - {subscriber_count} abonnés, {video_count} vidéos"
            if creation_date:
                message += f", créé le {creation_date}"
                
            return {
                "platform": "youtube",
                "exists": True,
                "url": f"youtube.com/channel/{channel['id']}",
                "message": message,
                "details": {
                    "title": channel_title,
                    "subscribers": subscriber_count,
                    "videos": video_count,
                    "views": view_count,
                    "created": creation_date,
                    "description": description
                }
            }
        else:
            return {
                "platform": "youtube",
                "exists": False,
                "url": "youtube.com/@{}",
                "message": "Aucune chaîne YouTube trouvée pour cet identifiant"
            }
    except Exception as e:
        return {
            "platform": "youtube",
            "exists": None,
            "url": "youtube.com/@{}",
            "message": f"Error: {str(e)}"
        }
    
def check_wikipedia_username(username):
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
    }

    url = "https://en.wikipedia.org/wiki/Special:CentralAuth?target={}"
    response = requests.get(url.format(f"{username}"), headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    
    if "There is no global account for" in soup.prettify():
        return {
            "platform": "wikipedia",
            "exists": False,
            "url": url,
            "message": "Username not available"
        }
    else:
        return {
            "platform": "wikipedia",
            "exists": True,
            "url": url,
            "message": "Username available"
        }


def check_username_exists(username, positive_only=False):
    """
    Vérifie l'existence d'un nom d'utilisateur sur différentes plateformes.
    Utilise des fonctions spécialisées pour les plateformes problématiques.
    """
    results = {}
    
    # Vérifier sur Twitch
    twitch_result = check_twitch_username(username)
    results["twitch"] = twitch_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "twitch", twitch_result, positive_only)
    
    # Vérifier sur Instagram
    instagram_result = check_instagram_username(username)
    results["instagram"] = instagram_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "instagram", instagram_result, positive_only)
    
    # Vérifier sur Facebook
    facebook_result = check_facebook_username(username)
    results["facebook"] = facebook_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "facebook", facebook_result, positive_only)
    
    # Vérifier sur TryHackMe
    tryhackme_result = check_tryhackme_username(username)
    results["tryhackme"] = tryhackme_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "tryhackme", tryhackme_result, positive_only)
    
    # Vérifier sur Discord
    discord_result = check_discord_username(username)
    results["discord"] = discord_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "discord", discord_result, positive_only)
    
    # Vérifier sur Imginn
    imginn_result = check_imginn_username(username)
    results["imginn"] = imginn_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "imginn", imginn_result, positive_only)
    
    # Vérifier sur Medium
    medium_result = check_medium_username(username)
    results["medium"] = medium_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "medium", medium_result, positive_only)
    
    # Vérifier sur TikTok
    tiktok_result = check_tiktok_username(username)
    results["tiktok"] = tiktok_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "tiktok", tiktok_result, positive_only)
    
    # Vérifier sur Cracked
    cracked_result = check_cracked_username(username)
    results["cracked"] = cracked_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "cracked", cracked_result, positive_only)
    
    # Vérifier sur Reddit
    reddit_result = check_reddit_username(username)
    results["reddit"] = reddit_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "reddit", reddit_result, positive_only)
    
    # Vérifier sur Pinterest
    pinterest_result = check_pinterest_username(username)
    results["pinterest"] = pinterest_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "pinterest", pinterest_result, positive_only)
    
    # Vérifier sur Gravatar
    gravatar_result = check_gravatar_username(username)
    results["gravatar"] = gravatar_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "gravatar", gravatar_result, positive_only)
    
    # Vérifier sur HackenProof
    hackenproof_result = check_hackenproof_username(username)
    results["hackenproof"] = hackenproof_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "hackenproof", hackenproof_result, positive_only)

    # Vérifier sur Imginn (second check)
    imginn_result = check_imginn_username(username)
    results["imginn"] = imginn_result
    # Ne pas afficher à nouveau, résultat dupliqué

    # Vérifier sur Hackerrank
    hackerrank_result = check_hackerrank_username(username)
    results["hackerrank"] = hackerrank_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "hackerrank", hackerrank_result, positive_only)

    # Vérifier sur Hackerearth
    hackerearth_result = check_hackerearth_username(username)
    results["hackerearth"] = hackerearth_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "hackerearth", hackerearth_result, positive_only)

    # Vérifier sur WordPress
    wordpress_result = check_wordpress_username(username)
    results["wordpress"] = wordpress_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "wordpress", wordpress_result, positive_only)

    # Vérifier sur Youtube
    youtube_result = check_youtube_username(username)
    results["youtube"] = youtube_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "youtube", youtube_result, positive_only)

    # Vérifier sur Wikipedia
    wikipedia_result = check_wikipedia_username(username)
    results["wikipedia"] = wikipedia_result
    # Afficher le résultat immédiatement
    display_direct_check_result(username, "wikipedia", wikipedia_result, positive_only)

    return results

# Fonction pour afficher les résultats des vérifications directes
def display_direct_check_result(username, platform, result, positive_only=False):
    """Affiche le résultat d'une vérification directe"""
    # Ne pas afficher si mode positif uniquement et résultat non positif
    if positive_only and result.get("exists") != True:
        return
        
    if result.get("exists") == True:
        # Affichage de base
        print(f"{Fore.GREEN}{Style.BRIGHT}{username} is on {Fore.YELLOW}{Style.BRIGHT}{platform.upper()} {Fore.LIGHTBLUE_EX}{Style.BRIGHT} -> {Fore.WHITE}{Style.BRIGHT}{result.get('message')} on {result.get('url')}{Style.RESET_ALL}")
        
        # Afficher des détails supplémentaires si disponibles (comme pour YouTube)
        if platform.lower() == "youtube" and result.get("details"):
            details = result.get("details")
            if details.get("description"):
                print(f"{Fore.CYAN}  Description: {Fore.WHITE}{details.get('description')}{Style.RESET_ALL}")
            
            # Afficher un résumé des statistiques
            print(f"{Fore.CYAN}  Statistiques: {Fore.WHITE}{details.get('views', '?')} vues totales{Style.RESET_ALL}")
            
    elif result.get("exists") == False:
        print(f"{Fore.RED}{Style.BRIGHT}{username} is not on {Fore.YELLOW}{Style.BRIGHT}{platform.upper()}{Style.RESET_ALL}")
    else:
        print(f"{Fore.WHITE}{Style.BRIGHT}{username} status unknown on {Fore.YELLOW}{Style.BRIGHT}{platform.upper()}{Style.RESET_ALL}")
    if "error" in result:
        print(f"{Fore.RED}{Style.BRIGHT}[ERROR] {result.get('error')}{Style.RESET_ALL}")

class Watson:
    def __init__(self, max_workers=5, without_user_config=False):
        self.without_user_config = without_user_config
        self.sites = self._load_sites()
        self.categories = self._get_categories()
        self.browsers = self._load_browsers()
        self.max_workers = max_workers
        self.result_queue = Queue()
        self.lock = threading.Lock()
        init()  # Initialiser colorama

    def _load_browsers(self):
        """Charge les configurations des navigateurs depuis le fichier JSON"""
        try:
            browsers_file_path = get_resource_path('ressources/browsers.json')
            with open(browsers_file_path, 'r') as f:
                data = json.load(f)
                return data['browsers']
        except Exception as e:
            print(f"{Fore.RED}Erreur lors du chargement des navigateurs: {e}{Style.RESET_ALL}")
            return []

    def _get_random_browser(self):
        """Retourne une configuration aléatoire de navigateur"""
        if self.browsers:
            return random.choice(self.browsers)
        return None

    def _check_site(self, url, site_data, username):
        """Vérifie un site spécifique avec un navigateur aléatoire"""
        try:
            browser = self._get_random_browser()
            headers = {
                'User-Agent': browser['user_agent'],
                'Accept-Language': browser['accept_language'],
                'Accept': browser['accept']
            } if browser else {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            response = requests.get(url, headers=headers, allow_redirects=True)
            
            if isinstance(site_data['error'], dict):
                search_text = site_data['error']['response_text'].format(username)
                exists = search_text in response.text
            else:
                exists = response.status_code == 200

            result = {
                'exists': exists,
                'url': url,
                'name': site_data['name'],
                'message': site_data.get('message', ''),
                'category': site_data['category'],
                'browser': browser['name'] if browser else 'Default'
            }

            # Afficher le résultat en temps réel
            self._display_result(username, result)
            
            return result
            
        except Exception as e:
            result = {
                'exists': None,
                'url': url,
                'name': site_data['name'],
                'error': str(e),
                'category': site_data['category'],
                'browser': browser['name'] if browser else 'Default'
            }
            self._display_result(username, result)
            return result

    def _display_result(self, username, result):
        """Affiche un résultat en temps réel"""
        with self.lock:
            # Si l'option positive est activée, n'afficher que les résultats où exists est True
            if hasattr(self, 'positive_only') and self.positive_only and result.get('exists') != True:
                return
                
            if result.get('exists') == True:
                # Afficher le message personnalisé du site si disponible
                site_message = ""
                if result.get('message'):
                    site_message = f"{result.get('message')} "
                print(f"{Fore.GREEN}{Style.BRIGHT}{username} is on {Fore.YELLOW}{Style.BRIGHT}{result.get('name')} {Fore.LIGHTBLUE_EX}{Style.BRIGHT}-> {Fore.BLUE}{Style.BRIGHT}{site_message} {Fore.WHITE}{Style.BRIGHT}(Browser Used: {result.get('browser')}){Style.RESET_ALL}")
            elif result.get('exists') == False:
                print(f"{Fore.RED}{Style.BRIGHT}{username} is not on {Fore.YELLOW}{Style.BRIGHT}{result.get('name')}{Style.RESET_ALL}")
            else:
                print(f"{Fore.WHITE}{Style.BRIGHT}{username} status unknown on {Fore.YELLOW}{Style.BRIGHT}{result.get('name')}{Style.RESET_ALL}")
            if 'error' in result:
                print(f"{Fore.RED}{Style.BRIGHT}[ERROR] {result.get('error')}{Style.RESET_ALL}")

    def check_username(self, username):
        """Vérifie l'existence d'un username sur tous les sites en utilisant des threads"""
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for url_template, site_data in self.sites.items():
                url = url_template.format(username)
                future = executor.submit(self._check_site, url, site_data, username)
                futures.append(future)
            
            for future in futures:
                result = future.result()
                site_name = result.get('name')  # Utiliser le nom du site au lieu de l'URL
                results[site_name] = result
        
        return self._organize_by_category(results)

    def _load_sites(self):
        """Charge les sites depuis le fichier JSON"""
        sites = {}
        
        # Charger les sites principaux
        try:
            sites_file_path = get_resource_path('ressources/sites.json')
            with open(sites_file_path, 'r') as f:
                data = json.load(f)
                sites.update(data['sites'])
        except Exception as e:
            print(f"{Fore.RED}Erreur lors du chargement des sites principaux: {e}{Style.RESET_ALL}")
        
        # Charger les sites utilisateur s'ils existent (sauf si --without-config est spécifié)
        if not self.without_user_config:
            try:
                user_sites_path = get_resource_path('userConfig/user_sites.json')
                if os.path.exists(user_sites_path):
                    with open(user_sites_path, 'r') as f:
                        user_data = json.load(f)
                        if 'sites' in user_data:
                            sites.update(user_data['sites'])
                        else:
                            sites.update(user_data)  # Prend en charge le format sans "sites"
            except Exception as e:
                print(f"{Fore.YELLOW}Note: Aucun site utilisateur trouvé ou erreur lors du chargement: {e}{Style.RESET_ALL}")
        
        return sites
    
    def _get_categories(self):
        """Récupère toutes les catégories uniques"""
        categories = set()
        for site_data in self.sites.values():
            categories.add(site_data['category'])
        return sorted(list(categories))
    
    def _organize_by_category(self, results):
        """Organise les résultats par catégorie"""
        organized = {category: {} for category in self.categories}
        
        for site_name, result in results.items():
            category = result['category']
            organized[category][site_name] = result
        
        return organized
    
    def display_results(self, username, results):
        """Affiche les résultats par catégorie"""
        watson_ascii = """
██╗    ██╗ █████╗ ████████╗███████╗ ██████╗ ███╗   ██╗
██║    ██║██╔══██╗╚══██╔══╝██╔════╝██╔═══██╗████╗  ██║
██║ █╗ ██║███████║   ██║   ███████╗██║   ██║██╔██╗ ██║
██║███╗██║██╔══██║   ██║   ╚════██║██║   ██║██║╚██╗██║
╚███╔███╔╝██║  ██║   ██║   ███████║╚██████╔╝██║ ╚████║
 ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝ ╚═════╝ ╚═╝  ╚═══╝ Made by margoul1
"""
# Affichage dynamique du logo avec rotation des couleurs
        print(f"{Fore.YELLOW}{Style.BRIGHT}" + watson_ascii + f"{Style.RESET_ALL}")
        
        for category in self.categories:
            if results[category]:  # Si la catégorie contient des résultats
                print(f"\n{Fore.CYAN}{Style.BRIGHT}=== {category.upper()} ==={Style.RESET_ALL}")
                
                for site_name, result in results[category].items():
                    if result.get('exists') == True:
                        print(f"{Fore.GREEN}{Style.BRIGHT}{username} is on {Fore.YELLOW}{Style.BRIGHT}{site_name} {Fore.LIGHTBLUE_EX}{Style.BRIGHT}-> {Fore.WHITE}{Style.BRIGHT}{result.get('message', '')} on {result.get('url')}{Style.RESET_ALL}")
                    elif result.get('exists') == False:
                        print(f"{Fore.RED}{Style.BRIGHT}{username} is not on {Fore.YELLOW}{Style.BRIGHT}{site_name}{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.WHITE}{Style.BRIGHT}{username} status unknown on {Fore.YELLOW}{Style.BRIGHT}{site_name}{Style.RESET_ALL}")
                    if 'error' in result:
                        print(f"{Fore.RED}{Style.BRIGHT}[ERROR] {result.get('error')}{Style.RESET_ALL}")

def add_user_site():
    """Permet à l'utilisateur d'ajouter un site personnalisé"""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}=== Configuration de site personnalisé ==={Style.RESET_ALL}\n")
    
    # Vérifier l'existence du dossier userConfig
    if not os.path.exists('watson/userConfig'):
        os.makedirs('watson/userConfig')
    
    # Charger les sites existants
    user_sites = {}
    user_sites_path = 'watson/userConfig/user_sites.json'
    if os.path.exists(user_sites_path):
        try:
            with open(user_sites_path, 'r') as f:
                user_sites = json.load(f)
                # Vérifier si le format contient 'sites' ou directement les sites
                if 'sites' in user_sites:
                    sites_dict = user_sites['sites']
                else:
                    sites_dict = user_sites
                    user_sites = {'sites': sites_dict}
        except json.JSONDecodeError:
            # Si le fichier existe mais n'est pas un JSON valide, commencer avec un fichier vide
            user_sites = {'sites': {}}
    else:
        # Si le fichier n'existe pas, initialiser avec un dictionnaire vide
        user_sites = {'sites': {}}
    
    # Demander les informations du site
    site_url = input(f"{Fore.YELLOW}Site URL (use {{}}, here watson will check for the username (eg: https://google.com/users/{{}})) : {Style.RESET_ALL}")
    
    # Vérification de base de l'URL
    if not site_url or '{}' not in site_url:
        print(f"{Fore.RED}Error: URL has to contain {{}} to be used by watson {Style.RESET_ALL}")
        return
    
    site_name = input(f"{Fore.YELLOW}Site Name{Style.RESET_ALL}")
    if not site_name:
        print(f"{Fore.RED}Site Name Required{Style.RESET_ALL}")
        return
    
    print(f"\n{Fore.CYAN}Error Type : {Style.RESET_ALL}")
    print(f"{Fore.BLUE}To check if a username is valid or nah we have to check the response codes,status,messages,etc... it's often one of these two choose one of these options and watson will check for you if there is any user existing on your target site with the response code or message displayed in.")
    print(f"{Fore.BLUE}1. HTTP Code (default: 200 = exists, others = doesn't exists or has advandced protections (like Twitter))")
    print(f"2. Responses Message {Style.RESET_ALL}")
    error_type = input(f"{Fore.YELLOW}Choose one  (1/2) : {Style.RESET_ALL}")
    
    if error_type == '2':
        error_text = input(f"{Fore.YELLOW}Enter the message that will show if the user exists on the platform here :  {Style.RESET_ALL}")
        error = {"response_text": error_text}
    else:
        # Par défaut, utiliser le code HTTP
        error = "code"
    
    # Afficher les catégories disponibles pour référence
    print(f"\n{Fore.CYAN}Category : {Style.RESET_ALL}")
    # Récupérer les catégories existantes si possible
    categories = set()
    try:
        with open('./watson/ressources/sites.json', 'r') as f:
            data = json.load(f)
            for site_data in data['sites'].values():
                categories.add(site_data['category'])
    except:
        # Catégories de base si impossible de charger
        categories = {"social", "gaming", "adults", "cyber", "development", "website", "finance", "hosting", "forum"}
    
    # Afficher les catégories
    for i, category in enumerate(sorted(categories), 1):
        print(f"{Fore.BLUE}{i}. {category}{Style.RESET_ALL}")
    
    category = input(f"{Fore.YELLOW}Categories : You can enter a new category which will be savec in your watson tool. {Style.RESET_ALL}")
    if not category:
        category = "other"  # Catégorie par défaut si vide
    
    message = input(f"{Fore.YELLOW}Personnal message (will be displayed in the terminal if the target is found) : {Style.RESET_ALL}")
    
    # Créer l'entrée du site
    site_data = {
        "name": site_name,
        "error": error,
        "category": category
    }
    
    if message:
        site_data["message"] = message
    
    # Ajouter le site à la liste
    user_sites['sites'][site_url] = site_data
    
    # Enregistrer dans le fichier
    with open(user_sites_path, 'w') as f:
        json.dump(user_sites, f, indent=4)
    
    print(f"\n{Fore.GREEN}{Style.BRIGHT}Site '{site_name}' successfully added !{Style.RESET_ALL}")
    print(f"Configuration sauvegardée dans: {user_sites_path}")

def delete_user_site():
    """Permet à l'utilisateur de supprimer un site personnalisé par son nom"""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}=== Deleting Personnal Site ==={Style.RESET_ALL}\n")
    
    # Vérifier l'existence du fichier de configuration utilisateur
    user_sites_path = 'watson/userConfig/user_sites.json'
    if not os.path.exists(user_sites_path):
        print(f"{Fore.RED}No users config file found.{Style.RESET_ALL}")
        return
    
    # Charger les sites existants
    try:
        with open(user_sites_path, 'r') as f:
            user_sites = json.load(f)
            
            # Déterminer la structure du fichier
            if 'sites' in user_sites:
                sites_dict = user_sites['sites']
            else:
                sites_dict = user_sites
                user_sites = {'sites': sites_dict}
    except Exception as e:
        print(f"{Fore.RED}Erreur while loading users sites: {e}{Style.RESET_ALL}")
        return
    
    # Vérifier s'il y a des sites à supprimer
    if not sites_dict:
        print(f"{Fore.YELLOW}No perosnnal sites found.{Style.RESET_ALL}")
        return
    
    # Afficher les sites disponibles
    print(f"{Fore.CYAN}Available sites :{Style.RESET_ALL}")
    site_names = []
    for url, site_data in sites_dict.items():
        site_name = site_data.get('name')
        site_names.append((site_name, url))
        print(f"{Fore.BLUE}- {site_name} ({url}){Style.RESET_ALL}")
    
    # Demander le nom du site à supprimer
    site_to_delete = input(f"\n{Fore.YELLOW}Site to delete : {Style.RESET_ALL}")
    
    # Chercher et supprimer le site
    found = False
    urls_to_delete = []
    
    for name, url in site_names:
        if name.lower() == site_to_delete.lower():
            urls_to_delete.append(url)
            found = True
    
    if not found:
        print(f"{Fore.RED}Error: No site named '{site_to_delete}' was found.{Style.RESET_ALL}")
        return
    
    # Supprimer les sites trouvés
    for url in urls_to_delete:
        del sites_dict[url]
    
    # Enregistrer les modifications
    with open(user_sites_path, 'w') as f:
        json.dump(user_sites, f, indent=4)
    
    count = len(urls_to_delete)
    print(f"\n{Fore.GREEN}{Style.BRIGHT}{count} site(s) named '{site_to_delete}' successfully deleted !{Style.RESET_ALL}")

def configure_api_key(api_type, api_key):
    """Configure une clé API dans le fichier apikeys.json"""
    api_file_path = get_resource_path("ressources/apikeys.json")
    
    # Vérifier si le dossier ressources existe
    resource_dir = get_resource_path("ressources")
    if not os.path.exists(resource_dir):
        try:
            os.makedirs(resource_dir)
            print(f"{Fore.GREEN}Répertoire 'ressources' créé avec succès.{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}Erreur lors de la création du répertoire 'ressources': {str(e)}{Style.RESET_ALL}")
            return False
    
    # Charger les données existantes ou créer un nouveau dictionnaire
    api_data = {}
    if os.path.exists(api_file_path):
        try:
            with open(api_file_path, "r") as file:
                api_data = json.load(file)
        except Exception as e:
            print(f"{Fore.YELLOW}Avertissement: Impossible de charger le fichier API existant: {str(e)}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Création d'un nouveau fichier de configuration.{Style.RESET_ALL}")
    
    # Mettre à jour la clé API
    if api_type.upper() == "YOUTUBE":
        # Vérification basique de la clé API YouTube (commence typiquement par 'AIza')
        if not api_key.startswith("AIza"):
            print(f"{Fore.YELLOW}Avertissement: La clé API YouTube fournie ne semble pas avoir le format attendu (commence généralement par 'AIza').{Style.RESET_ALL}")
            confirmation = input(f"{Fore.YELLOW}Voulez-vous continuer quand même? (o/n): {Style.RESET_ALL}").lower()
            if confirmation != 'o':
                print(f"{Fore.RED}Configuration annulée.{Style.RESET_ALL}")
                return False
        
        # Optionnel: Tester la clé API avant de la sauvegarder
        try:
            print(f"{Fore.BLUE}Test de la clé API YouTube...{Style.RESET_ALL}")
            youtube = build('youtube', 'v3', developerKey=api_key)
            request = youtube.channels().list(part="snippet", forUsername="Google")
            response = request.execute()
            if 'items' in response:
                print(f"{Fore.GREEN}La clé API YouTube est valide et fonctionne correctement.{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}La clé API a été acceptée mais pourrait avoir des limitations.{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}Erreur lors du test de la clé API: {str(e)}{Style.RESET_ALL}")
            confirmation = input(f"{Fore.YELLOW}Voulez-vous enregistrer cette clé quand même? (o/n): {Style.RESET_ALL}").lower()
            if confirmation != 'o':
                print(f"{Fore.RED}Configuration annulée.{Style.RESET_ALL}")
                return False
        
        api_data["yt_apikey"] = api_key
        print(f"{Fore.GREEN}{Style.BRIGHT}Clé API YouTube configurée avec succès !{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}{Style.BRIGHT}Type d'API non pris en charge : {api_type}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}{Style.BRIGHT}Types d'API pris en charge : YOUTUBE{Style.RESET_ALL}")
        return False
    
    # Enregistrer les modifications
    try:
        with open(api_file_path, "w") as file:
            json.dump(api_data, file, indent=4)
        print(f"{Fore.GREEN}Configuration sauvegardée dans {api_file_path}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Erreur lors de l'enregistrement de la configuration: {str(e)}{Style.RESET_ALL}")
        return False
    
    return True

# Créer une fonction main() à la fin du fichier
def main():
    """Point d'entrée principal pour le package Watson OSINT"""
    # Initialiser colorama
    init()
    
    # Créer le parseur d'arguments
    parser = argparse.ArgumentParser(description="Watson OSINT - Multi-plateforme username checker")
    parser.add_argument("username", nargs="?", help="just type the username you want to check")
    parser.add_argument("--final-logs", action="store_true", help="Display final detailed logs")
    parser.add_argument("--json", action="store_true", help="Generate JSON output instead of text")
    parser.add_argument("--config-site", action="store_true", help="Add a custom site to user configuration")
    parser.add_argument("--config-site-del", action="store_true", help="Delete a custom site from user configuration")
    parser.add_argument("--config-apikey", action="store_true", help="Configure API Key for advanced features")
    parser.add_argument("--positive", action="store_true", help="Display only existing accounts")
    parser.add_argument("--buster", action="store_true", help="Use miniBuster to check additional URLs")
    parser.add_argument("--speed", choices=["slow", "fast"], default="fast", help="Speed option for miniBuster (slow or fast, default: fast)")
    parser.add_argument("-f", "--file", help="Path to URL list file for miniBuster")
    args = parser.parse_args()
    
    # Gérer les options de configuration
    if args.config_site:
        add_user_site()
        return
    
    if args.config_site_del:
        delete_user_site()
        return
    
    if args.config_apikey:
        if not args.username:
            print(f"{Fore.RED}Error: You must specify an API type (youtube, twitter, etc.){Style.RESET_ALL}")
            return
        if len(sys.argv) < 3:
            print(f"{Fore.RED}Error: You must specify the API key{Style.RESET_ALL}")
            return
        api_type = args.username
        api_key = sys.argv[2]
        configure_api_key(api_type, api_key)
        return
    
    if args.username and args.buster:
        if not args.file:
            print(f"{Fore.RED}Error: You must specify a URL list file with -f when using --buster{Style.RESET_ALL}")
            return
        if not args.speed:
            print(f"{Fore.RED}Error: You must specify a speed with --speed fast|slow when using --buster{Style.RESET_ALL}")
            return

    
    # Vérifier si un nom d'utilisateur a été fourni
    if not args.username:
        parser.print_help()
        return
    
    username = args.username
    
    # Afficher le logo et les informations de démarrage
                                                                           
    print(f"{Fore.GREEN}{Style.BRIGHT}")                                                           
    print("                                  ")
    print("           .---.               ___                                     ")
    print("          /. ./|             ,--.'|_                                   ")
    print("      .--'.  ' ;             |  | :,'              ,---.        ,---,  ")
    print("     /__./ \\ : |             :  : ' :  .--.--.    '   ,'\\   ,-+-. /  | ")
    print(" .--'.  '   \\' .  ,--.--.  .;__,'  /  /  /    '  /   /   | ,--.'|'   | ")
    print("/___/ \\ |    ' ' /       \\ |  |   |  |  :  /`./ .   ; ,. :|   |  ,\"' | ")
    print(";   \\  \\;      :.--.  .-. |:__,'| :  |  :  ;_   '   | |: :|   | /  | | ")
    print(" \\   ;  `      | \\__\\/: . .  '  : |__ \\  \\    `.'   | .; :|   | |  | | ")
    print("  .   \\    .\\  ; ,\" .--.; |  |  | '.'| `----.   \\   :    ||   | |  |/  ")
    print("   \\   \\   ' \\ |/  /  ,.  |  ;  :    ;/  /`--'  /\\   \\  / |   | |--'   ")
    print("    :   '  |--\\\";  :   .'   \\ |  ,   /'--'.     /  `----'  |   |/       ")
    print("     \\   \\ ;   |  ,     .-./  ---`-'   `--'---'           '---'        ")
    print("      '---\"     `--`---'                                               ")
    print(f"{Fore.WHITE}{Style.BRIGHT}[+] Watson v0.2 - margoul1{Style.RESET_ALL}")
                                                     
    """ print(f"{Fore.GREEN}{Style.BRIGHT}")
    print(" _       __      __                   ")
    print("| |     / /___ _/ /________  ____    ")
    print("| | /| / / __ `/ __/ ___/ / / / _ \\ ")
    print("| |/ |/ / /_/ / /_(__  ) /_/ /  __/  ")
    print("|__/|__/\\__,_/\\__/____/\\__,_/\\___/ ")
    print(f"{Style.RESET_ALL}")
    print(f"{Fore.WHITE}{Style.BRIGHT}[+] Watson v0.1 - GodEyes OSINT Team{Style.RESET_ALL}") """
    
    # Vérification avec check_username_exists pour les services spécifiques
    check_username_exists(username, args.positive)
    
    # Utiliser la vérification complète avec le moteur Watson
    watson = Watson()
    # Définir l'attribut positive_only pour Watson
    watson.positive_only = args.positive
    
    # Continuer avec la vérification Watson standard
    watson_results = watson.check_username(username)
    
    # Si miniBuster est demandé
    if args.buster:
        if not args.file:
            print(f"{Fore.RED}Error: You must specify a URL list file with -f when using --buster{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.CYAN}{Style.BRIGHT}=== Running MiniBuster ==={Style.RESET_ALL}")
            
            # Déterminer le chemin absolu du fichier d'URLs
            if not os.path.isabs(args.file):
                # Si c'est un chemin relatif, le convertir en chemin absolu
                file_path = os.path.abspath(args.file)
            else:
                file_path = args.file
            
            # Vérifier que le fichier existe
            if not os.path.exists(file_path):
                print(f"{Fore.RED}Error: URL list file not found at {file_path}{Style.RESET_ALL}")
                return
            
            # Lire le fichier d'URLs
            try:
                with open(file_path, 'r') as f:
                    urls = [line.strip() for line in f if line.strip()]
                
                # Afficher les informations
                print(f"{Fore.CYAN}[*] Testing paths for {username} on multiple URLs{Style.RESET_ALL}")
                print(f"{Fore.CYAN}[*] Mode de vitesse: {args.speed}{Style.RESET_ALL}")
                
                # Créer un dossier pour les logs s'il n'existe pas
                if not os.path.exists('logs'):
                    os.makedirs('logs')
                
                # Définir les chemins possibles à tester
                paths = [
                    f"/users/{username}",
                    f"/user/{username}",
                    f"/profile/{username}",
                    f"/account/{username}",
                    f"/settings/{username}",
                    f"/dashboard/{username}",
                    f"/people/{username}",
                    f"/@{username}",
                    f"/users/@{username}",
                    f"/user/@{username}",
                    f"/profile/@{username}",
                    f"/account/@{username}",
                    f"/settings/@{username}",
                    f"/dashboard/@{username}",
                    f"/people/@{username}",
                    f"/{username}",
                    f"/u/{username}",
                    f"/p/{username}",
                    f"/a/{username}",
                    f"/s/{username}",
                    f"/d/{username}",
                    f"/member/{username}",
                    f"/members/{username}",
                    f"/profile.php?user={username}",
                    f"/user.php?name={username}",
                    f"/profile.php?username={username}",
                    f"/user.php?username={username}",
                    f"/profile.php?id={username}",
                    f"/user.php?id={username}",
                    f"/profile/{username}/",
                    f"/user/{username}/",
                    f"/account/{username}/",
                    f"/settings/{username}/",
                    f"/dashboard/{username}/",
                    f"/people/{username}/",
                    f"/@{username}/",
                    f"/users/@{username}/",
                    f"/user/@{username}/",
                    f"/profile/@{username}/",
                    f"/account/@{username}/",
                    f"/settings/@{username}/",
                    f"/dashboard/@{username}/",
                    f"/people/@{username}/",
                    f"/{username}/",
                    f"/u/{username}/",
                    f"/p/{username}/",
                    f"/a/{username}/",
                    f"/s/{username}/",
                    f"/d/{username}/",
                    f"/member/{username}/",
                    f"/members/{username}/",
                    f"/admin/{username}",
                    f"/admin/@{username}",
                    f"/admin/{username}/",
                    f"/admin/@{username}/",
                    f"/mod/{username}",
                    f"/mod/@{username}",
                    f"/mod/{username}/",
                    f"/mod/@{username}/",
                    f"/staff/{username}",
                    f"/staff/@{username}",
                    f"/staff/{username}/",
                    f"/staff/@{username}/",
                    f"/view/{username}",
                    f"/view/@{username}",
                    f"/view/{username}/",
                    f"/view/@{username}/",
                    f"/show/{username}",
                    f"/show/@{username}",
                    f"/show/{username}/",
                    f"/show/@{username}/",
                    f"/public/{username}",
                    f"/public/@{username}",
                    f"/public/{username}/",
                    f"/public/@{username}/",
                    f"/private/{username}",
                    f"/private/@{username}",
                    f"/private/{username}/",
                    f"/private/@{username}/",
                    f"/home/{username}",
                    f"/home/@{username}",
                    f"/home/{username}/",
                    f"/home/@{username}/",
                    f"/page/{username}",
                    f"/page/@{username}",
                    f"/page/{username}/",
                    f"/page/@{username}/",
                    f"/info/{username}",
                    f"/info/@{username}",
                    f"/info/{username}/",
                    f"/info/@{username}/",
                    f"/details/{username}",
                    f"/details/@{username}",
                    f"/details/{username}/",
                    f"/details/@{username}/",
                    f"/about/{username}",
                    f"/about/@{username}",
                    f"/about/{username}/",
                    f"/about/@{username}/",
                    f"/me/{username}",
                    f"/me/@{username}",
                    f"/me/{username}/",
                    f"/me/@{username}/"
                ]
                
                # Définir l'en-tête HTTP
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                }
                
                # Pour chaque URL, tester les chemins
                for url in urls:
                    print(f"\n{Fore.YELLOW}[*] Testing URL: {url}{Style.RESET_ALL}")
                    for path in paths:
                        # Déterminer l'URL complète à tester
                        full_url = f"{url.rstrip('/')}{path}"
                        
                        try:
                            # Ajouter un délai pour éviter d'être bloqué
                            if args.speed == "slow":
                                time.sleep(random.uniform(0.5, 1.0))
                            else:
                                time.sleep(random.uniform(0.1, 0.3))
                                
                            # Envoyer la requête et mesurer le temps de réponse
                            start_time = time.time()
                            response = requests.get(full_url, headers=headers, timeout=10, allow_redirects=True)
                            elapsed_time = time.time() - start_time
                            status = response.status_code
                            
                            # Analyser la réponse
                            if status == 200:
                                print(f"{Fore.GREEN}[+] {full_url} - Status: {status} - Time: {elapsed_time:.3f}s{Style.RESET_ALL}")
                            elif status in [301, 302, 303, 307, 308]:
                                print(f"{Fore.YELLOW}[>] {full_url} - Status: {status} - Time: {elapsed_time:.3f}s -> {response.headers.get('Location', 'No redirect location')}{Style.RESET_ALL}")
                            else:
                                print(f"{Fore.RED}[-] {full_url} - Status: {status} - Time: {elapsed_time:.3f}s{Style.RESET_ALL}")
                                
                        except requests.RequestException as e:
                            print(f"{Fore.RED}[!] {full_url} - Error: {str(e)}{Style.RESET_ALL}")
                
                print(f"\n{Fore.CYAN}[*] Test terminé.{Style.RESET_ALL}")
                
            except Exception as e:
                print(f"{Fore.RED}Error executing MiniBuster: {str(e)}{Style.RESET_ALL}")
    
    # Afficher le rapport final uniquement si l'option est activée
    if args.final_logs and not args.json:
        # Si l'option --positive est activée, filtrer les résultats pour n'afficher que les positifs
        if args.positive:
            filtered_results = {}
            for category in watson_results:
                filtered_category = {}
                for site_name, result in watson_results[category].items():
                    if result.get('exists') == True:
                        filtered_category[site_name] = result
                if filtered_category:
                    filtered_results[category] = filtered_category
            watson.display_results(username, filtered_results)
        else:
            watson.display_results(username, watson_results)
    
    # Si la sortie JSON est demandée, afficher le JSON
    if args.json:
        import json as json_lib
        # Générer et afficher le JSON
        print(json_lib.dumps(watson_results, indent=4))
    
    # Afficher la section des sites intéressants que Watson ne peut pas atteindre
    print(f"\n{Fore.CYAN}{Style.BRIGHT}=== Interesting websites Watson (and any other tools even if they say it) can't reach ==={Style.RESET_ALL}")
    interesting_sites = [
        {"name": "PyPi", "url": "https://pypi.org/user/{}", "reason": "Anti-Bot to fat"},
        {"name": "X", "url": "https://x.com/{}", "reason": "Anti-Bot to fat"},
        {"name": "Steam Community Groups", "url": "https://steamcommunity.com/groups/{}", "reason": "Anti-Bot to fat"},
        {"name": "Steam Community ID", "url": "https://steamcommunity.com/id/{}", "reason": "Anti-Bot to fat"},
        {"name": "Soloby", "url": "http://www.soloby.ru/user/{}", "reason": "Anti-Bot to fat"}
    ]
    
    for site in interesting_sites:
        print(f"{Fore.YELLOW}{Style.BRIGHT}• {site['name']} {Fore.WHITE}{Style.BRIGHT}({site['reason']}){Style.RESET_ALL}")

    # N'afficher l'art ASCII qu'une seule fois, à la fin (sorti de la boucle)
    got_watsonned_ascii = """
  ▄████  ▒█████  ▄▄▄█████▓    █     █░ ▄▄▄     ▄▄▄█████▓  ██████  ▒█████   ███▄    █  ███▄    █ ▓█████ ▓█████▄ 
 ██▒ ▀█▒▒██▒  ██▒▓  ██▒ ▓▒   ▓█░ █ ░█░▒████▄   ▓  ██▒ ▓▒▒██    ▒ ▒██▒  ██▒ ██ ▀█   █  ██ ▀█   █ ▓█   ▀ ▒██▀ ██▌
▒██░▄▄▄░▒██░  ██▒▒ ▓██░ ▒░   ▒█░ █ ░█ ▒██  ▀█▄ ▒ ▓██░ ▒░░ ▓██▄   ▒██░  ██▒▓██  ▀█ ██▒▓██  ▀█ ██▒▒███   ░██   █▌
░▓█  ██▓▒██   ██░░ ▓██▓ ░    ░█░ █ ░█ ░██▄▄▄▄██░ ▓██▓ ░   ▒   ██▒▒██   ██░▓██▒  ▐▌██▒▓██▒  ▐▌██▒▒▓█  ▄ ░▓█▄   ▌
░▒▓███▀▒░ ████▓▒░  ▒██▒ ░    ░░██▒██▓  ▓█   ▓██▒ ▒██▒ ░ ▒██████▒▒░ ████▓▒░▒██░   ▓██░▒██░   ▓██░░▒████▒░▒████▓ 
 ░▒   ▒ ░ ▒░▒░▒░   ▒ ░░      ░ ▓░▒ ▒   ▒▒   ▓▒█░ ▒ ░░   ▒ ▒▓▒ ▒ ░░ ▒░▒░▒░ ░ ▒░   ▒ ▒ ░ ▒░   ▒ ▒ ░░ ▒░ ░ ▒▒▓  ▒ 
  ░   ░   ░ ▒ ▒░     ░         ▒ ░ ░    ▒   ▒▒ ░   ░    ░ ░▒  ░ ░  ░ ▒ ▒░ ░ ░░   ░ ▒░░ ░░   ░ ▒░ ░ ░  ░ ░ ▒  ▒ 
░ ░   ░ ░ ░ ░ ▒    ░           ░   ░    ░   ▒    ░      ░  ░  ░  ░ ░ ░ ▒     ░   ░ ░    ░   ░ ░    ░    ░ ░  ░ 
      ░     ░ ░                  ░          ░  ░              ░      ░ ░           ░          ░    ░  ░   ░    
                                                                                                        ░      
"""
    # Affichage dynamique du logo avec rotation des couleurs
    print(f"{Fore.YELLOW}{Style.BRIGHT}" + got_watsonned_ascii + f"{Style.RESET_ALL}")