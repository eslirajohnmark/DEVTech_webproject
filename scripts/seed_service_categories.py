"""Seed the nine service categories shown in the reference design.

Creates categories with colors, icons, and per-category service lists.
Idempotent — updates existing categories in place, doesn't duplicate.

Usage:
    python -m scripts.seed_service_categories
"""
from app import app, db, ServiceCategory, Service


CATEGORIES = [
    {
        'name': 'Hardware Repair & Replacement',
        'slug': 'hardware',
        'color': '#2563eb',
        'icon': 'fa-microchip',
        'display_order': 1,
        'description': 'Fix or replace physical computer components.',
        'services': [
            'Laptop/Desktop repair',
            'Keyboard replacement',
            'Screen/LCD replacement',
            'Battery replacement',
            'RAM installation or replacement',
            'Hard drive/SSD replacement',
            'Power supply replacement',
            'Motherboard repair',
            'Cooling fan replacement',
            'Overheating and thermal-paste service',
            'Computer cleaning and dust removal',
        ],
    },
    {
        'name': 'Software & Operating System Services',
        'slug': 'software',
        'color': '#8b5cf6',
        'icon': 'fa-windows',
        'display_order': 2,
        'description': 'Solve software issues and keep your system running smoothly.',
        'services': [
            'Windows installation/reinstallation',
            'Operating system troubleshooting',
            'Driver installation',
            'Software installation',
            'Software configuration',
            'Application troubleshooting',
            'System error fixing',
            'Startup/boot problem repair',
            'Blue-screen/error troubleshooting',
            'System optimization',
        ],
    },
    {
        'name': 'Virus & Security Services',
        'slug': 'security',
        'color': '#10b981',
        'icon': 'fa-shield-virus',
        'display_order': 3,
        'description': 'Remove threats and protect your data.',
        'services': [
            'Virus and malware removal',
            'Antivirus installation',
            'Security configuration',
            'Malware scanning',
            'Browser hijacker removal',
            'Account/security troubleshooting',
            'Basic data-security assessment',
        ],
    },
    {
        'name': 'Data & Storage Services',
        'slug': 'data',
        'color': '#f59e0b',
        'icon': 'fa-database',
        'display_order': 4,
        'description': 'Backup, recover and manage your files and storage devices.',
        'services': [
            'Data backup',
            'Data transfer',
            'File recovery',
            'Hard-drive/SSD cloning',
            'Storage upgrade',
            'Data migration',
            'Basic recovery from corrupted storage',
        ],
        'tagline': 'Data recovery can be technically difficult, so we list '
                   'it as a service without guaranteeing successful recovery.',
    },
    {
        'name': 'Network & Internet Services',
        'slug': 'network',
        'color': '#06b6d4',
        'icon': 'fa-wifi',
        'display_order': 5,
        'description': 'Fix connectivity and network related issues.',
        'services': [
            'Wi-Fi troubleshooting',
            'Router configuration',
            'LAN setup',
            'Network troubleshooting',
            'Internet connection troubleshooting',
            'Basic network security configuration',
        ],
    },
    {
        'name': 'Maintenance & Optimization',
        'slug': 'maintenance',
        'color': '#7c3aed',
        'icon': 'fa-cog',
        'display_order': 6,
        'description': 'Keep your device clean, fast and running efficiently.',
        'services': [
            'Computer cleaning',
            'Preventive maintenance',
            'Performance optimization',
            'System health check',
            'Hardware inspection',
            'Temperature monitoring',
            'Startup optimization',
            'General computer tune-up',
        ],
    },
    {
        'name': 'Peripheral & Device Services',
        'slug': 'peripheral',
        'color': '#ec4899',
        'icon': 'fa-print',
        'display_order': 7,
        'description': 'Repair or configure your accessories and external devices.',
        'services': [
            'Printer troubleshooting',
            'Monitor troubleshooting',
            'Keyboard/mouse problems',
            'Webcam setup',
            'Speaker/audio troubleshooting',
            'External hard-drive troubleshooting',
            'Peripheral installation and configuration',
        ],
    },
    {
        'name': 'Home-Service / On-Site Repair',
        'slug': 'onsite',
        'color': '#0ea5e9',
        'icon': 'fa-house-chimney',
        'display_order': 8,
        'description': 'We come to you! Book a technician for your location.',
        'services': [
            'Computer troubleshooting',
            'Hardware inspection',
            'Software troubleshooting',
            'Network/Wi-Fi setup',
            'Printer setup',
            'Device installation',
            'Preventive maintenance',
        ],
    },
    {
        'name': 'Computer Upgrade Services',
        'slug': 'upgrade',
        'color': '#059669',
        'icon': 'fa-arrow-up-right-dots',
        'display_order': 9,
        'description': 'Improve performance with upgrades and enhancements.',
        'services': [
            'RAM upgrade',
            'SSD upgrade',
            'HDD-to-SSD upgrade',
            'Graphics card installation',
            'CPU/cooling upgrade',
            'Cooling-system upgrade',
            'Operating-system upgrade',
            'Hardware compatibility assessment',
        ],
    },
]


def main():
    with app.app_context():
        for spec in CATEGORIES:
            cat = ServiceCategory.query.filter_by(slug=spec['slug']).first()
            if not cat:
                cat = ServiceCategory(name=spec['name'], slug=spec['slug'])
                db.session.add(cat)
                print(f'  add   {spec["slug"]}')
            else:
                print(f'  update {spec["slug"]}')

            cat.name = spec['name']
            cat.description = spec.get('description', '')
            cat.color = spec['color']
            cat.icon = spec['icon']
            cat.display_order = spec['display_order']
            cat.tagline = spec.get('tagline', '')
            cat.is_active = True
            db.session.flush()

            for svc_name in spec['services']:
                existing = Service.query.filter_by(
                    category_id=cat.id, name=svc_name).first()
                if not existing:
                    db.session.add(Service(
                        category_id=cat.id,
                        name=svc_name,
                        description='',
                        price=0,
                        estimated_hours=1,
                        is_active=True,
                    ))

        db.session.commit()
        print()
        print('Seeded 9 service categories.')
        print('Visit /user/services after starting the app.')


if __name__ == '__main__':
    main()