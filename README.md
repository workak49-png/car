# Машина гонкасы 3D

Pygame менен жасалган псевдо-3D гонка оюну (OutRun стилинде): жол алдыга созулат, ийримдер, дөбөлөр, тоолор, токойлор жана күн батуу бар. Сүрөт же үн файлдары керек эмес, бардыгы коддун өзүндө чийилет.

## Иштетүү

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux / macOS

pip install -r requirements.txt
python main.py
```

## Башкаруу

| Баскыч | Аракет |
| --- | --- |
| ↑ / W | Газ |
| ↓ / S | Тормоз |
| ← → / A D | Бурулуу |
| SPACE | Баштоо |
| P | Тыным |
| R | Кайра баштоо |
| ESC | Чыгуу |

## Оюндун эрежеси

- Убакыт кемий берет. Турду бүтүрсөң +45 сек кошулат.
- Тыйындарды чогулт: ар бири +100 упай жана +0.5 сек.
- Башка машинага тийсең ылдамдыгың кескин түшөт.
- Жолдон чыгып кетсең ылдамдык азаят, дарактарга тийсең дээрлик токтойсуң.
- Убакыт бүтсө оюн бүтөт.

## GitHub'ка салуу

```bash
git init
git add .
git commit -m "First commit"
git branch -M main
git remote add origin https://github.com/ЛОГИН/РЕПО.git
git push -u origin main
```
