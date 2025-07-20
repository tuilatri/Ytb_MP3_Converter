import json

# Read the JSON cookies file
with open('D:\\Ytb_MP3_Converter\\cookies.txt', 'r') as f:
    cookies = json.load(f)

# Write to Netscape format
with open('D:\\Ytb_MP3_Converter\\cookies_netscape.txt', 'w') as f:
    f.write('# Netscape HTTP Cookie File\n')
    f.write('# This is a generated file! Do not edit.\n\n')
    for cookie in cookies:
        domain = cookie['domain']
        include_subdomains = 'TRUE' if not cookie['hostOnly'] else 'FALSE'
        path = cookie['path']
        secure = 'TRUE' if cookie['secure'] else 'FALSE'
        expiry = int(cookie['expirationDate']) if 'expirationDate' in cookie else 0
        name = cookie['name']
        value = cookie['value']
        f.write(f'{domain}\t{include_subdomains}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n')

print('Converted cookies to Netscape format: cookies_netscape.txt')