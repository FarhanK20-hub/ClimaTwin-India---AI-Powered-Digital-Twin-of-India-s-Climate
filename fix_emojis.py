import os

emojis = ['🗺️', '📉', '🤖', '🛰️', '🌿', '🌡️', '🌧️', '🔥', '🏜️', '⏳', '📈', '⚠️', '💧', '🌾', '🏞️', '👥', '📊', '🏗️', '🔍', '📡', '📍', '🌏', '☁️', '⚡', '✅']

for fpath in ['frontend/index.html', 'frontend/app.js', 'frontend/style.css']:
    if not os.path.exists(fpath):
        continue
    with open(fpath, 'r', encoding='utf-8') as f:
        t = f.read()
    
    for e in emojis:
        t = t.replace(e + ' ', '').replace(e, '')
    
    t = t.replace(' — ', ' - ').replace('—', '-')
    
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(t)

print('Done!')
