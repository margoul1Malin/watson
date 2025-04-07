# Watson OSINT

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Watson OSINT est un outil puissant pour rechercher des noms d'utilisateur sur de multiples plateformes en ligne. Il permet de détecter rapidement la présence d'un utilisateur sur différents sites web, réseaux sociaux et plateformes.

## Fonctionnalités

- Search for usernames comprehensively (Response Status, Response Core, Response Time, XHR Calls, API, etc..)
- Results in real-time, works well with the godsEye Project
- JSON Reports availables
- Easy user config

## Installation

```bash
pip install watson-osint
```

Clone git repository : 

```bash
git clone https://github.com/margoul1/watson.git
cd watson
pip install -e .
```

## Usage

### Basic Syntax

```bash
watson username
```

### Options disponibles

- `--final-logs` : Show Final Report
- `--json` : Show jsonified logs
- `--config-site` : Add a site you want to scan
- `--config-site-del` : Del a site you've previously added
- `--config-apikey` : API configuration for scanning youtube accounts
- `--positive` : Show only [Positive Results]
- '--buster' : Use miniBuster who's able to scan for subdomain and bruteforce all usernames's relative path on a target.
- '--speed' : miniBuster's speed (slow | fast)
- '-f' : Path file to your urls.txt for miniBuster (he's able to scan a list of urls but it might take longer time)
### Exemples

Simple search : 
```bash
watson johndoe
```

Show only positive results
```bash
watson johndoe --positive
```

Get a json report : 
```bash
watson johndoe --json > resultats.json
```

Configure Youtube API :
```bash
watson --config-apikey YOUTUBE your_api_key
```

Use miniBuster : 
```bash
watson --buster --speed fast -f path/to/urls.txt johndoe
```

## Licence

This projects is under MIT License - show [LICENSE](LICENSE) for more details.

## Auteur

Developped by [margoul1](https://github.com/margoul1)
