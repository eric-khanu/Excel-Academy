# Staff ID Card Generator

A Django application for generating, managing, and printing professional staff ID cards. Supports double-sided cards with QR codes, bulk CSV import, and full customization of school branding.

## Features

- 🎨 **Customizable branding** — school name, logo, colors
- 🆔 **Auto-generated employee IDs** — `EJSS-2026-001` format
- 👤 **Full staff management** — roles, departments, levels
- 📇 **Double-sided cards** — front + back with unique layouts
- 🖨️ **Print-ready** — CR80 sizing (2.125" × 3.375")
- 📄 **PDF export** — single card or bulk
- 📊 **Bulk CSV import**
- 📱 **QR codes** — encode employee ID on the back
- 🏫 **Multi-department & level support**

## Tech Stack

- **Backend**: Django 5.x
- **Database**: SQLite (dev) — swap for PostgreSQL in production
- **PDF**: xhtml2pdf
- **QR**: qrcode[pil]
- **Images**: Pillow

## Local Setup

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/staff-id-generator.git
cd staff-id-generator

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create a .env file (see .env.example)

# 5. Run migrations
python manage.py migrate

# 6. Create a superuser
python manage.py createsuperuser

# 7. Run the server
python manage.py runserver