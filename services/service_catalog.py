"""DEVTech's service catalog: what an ordinary computer repair shop offers.

sync_service_catalog() brings the service_categories / services tables in line
with CATALOG without duplicating anything:
  - categories are found by slug (or old name) and renamed in place, so ids,
    slugs/URLs and bookings stay as they are;
  - services are found by name or by an old name (`was`) and renamed /
    re-described in place; their price, duration and active state are kept,
    so configured prices and booking history are untouched;
  - services that don't exist yet are added with price 0, which the site shows
    as "Price upon diagnosis" (no prices are invented here);
  - anything an admin added that isn't listed here is left alone.
It is safe to run more than once. Used by init_db() for a new database and by
`flask --app app sync-service-catalog` for an existing one. It does not run on
every start, so later edits made in Admin > Services are not overwritten.
"""
from sqlalchemy import func

# hours = typical time for a straightforward job; admins can change it.
# price = the project's original default price, used only when the service is
# first created (a new database); everything else starts at 0 = price upon diagnosis.
CATALOG = [
    {
        'slug': 'accessory-replacement', 'was': ['Accessory Replacement'],
        'name': 'Accessory Replacement', 'icon': 'fa-plug',
        'description': 'Replace worn or faulty laptop parts, peripherals and cables.',
        'tagline': 'Replacement parts are priced separately and depend on your device model and stock availability.',
        'services': [
            {'name': 'Laptop Charger / Power Adapter Replacement', 'was': ['Charger Adapter Replacement'], 'hours': 1, 'price': 1200,
             'description': 'Test your charger and replace it with a compatible adapter of the correct wattage for your laptop.'},
            {'name': 'Laptop Keyboard Replacement', 'hours': 2,
             'description': 'Replace a laptop keyboard with missing, stuck or unresponsive keys with a compatible part.'},
            {'name': 'Laptop Touchpad Replacement', 'hours': 2,
             'description': 'Replace a touchpad that no longer clicks or tracks, after checking it is not a driver problem.'},
            {'name': 'Wired or Wireless Mouse Replacement', 'hours': 1,
             'description': 'Set up a replacement wired, USB-receiver or Bluetooth mouse and check it works with your computer.'},
            {'name': 'Computer Keyboard Replacement', 'hours': 1,
             'description': 'Set up a replacement wired or wireless desktop keyboard, including its receiver or pairing.'},
            {'name': 'Laptop Speaker Replacement', 'hours': 2,
             'description': 'Replace crackling or silent internal laptop speakers once audio drivers have been ruled out.'},
            {'name': 'Webcam Replacement', 'hours': 1,
             'description': 'Replace a faulty external webcam, or a laptop built-in camera where the part is available.'},
            {'name': 'Power Cable and HDMI Cable Replacement', 'hours': 1,
             'description': 'Replace damaged power, HDMI, DisplayPort or VGA cables and confirm the connection works.'},
            {'name': 'Laptop Battery Replacement', 'was': ['Battery Replacement'], 'hours': 1, 'price': 1800,
             'description': 'Replace a laptop battery that no longer holds a charge or is swelling, using a compatible battery.'},
            {'name': 'Desktop Monitor Replacement', 'hours': 1,
             'description': 'Install and set up a replacement monitor, including cables, resolution and display settings.'},
        ],
    },
    {
        'slug': 'data-recovery', 'was': ['Data Recovery'],
        'name': 'Data Recovery and Backup', 'icon': 'fa-database',
        'description': 'Recover lost files, back up your data and move it to a new computer.',
        'tagline': 'Data recovery is not guaranteed. Physically damaged, encrypted or failed drives may need a specialist '
                   'recovery laboratory; we tell you what is possible after diagnosis.',
        'services': [
            {'name': 'Deleted File Recovery', 'hours': 2,
             'description': 'Attempt to recover recently deleted files from a working drive. Stop using the drive to '
                            'improve the chances. Recovery is not guaranteed.'},
            {'name': 'HDD File Recovery', 'was': ['Data Recovery'], 'hours': 3, 'price': 5000,
             'description': 'Recover files from a hard disk drive that still spins and is detected. A drive with physical '
                            'damage may need a specialist laboratory. Recovery is not guaranteed.'},
            {'name': 'SSD Data Recovery Assessment', 'hours': 2,
             'description': 'Check whether data on a failing SSD can be read. SSDs with TRIM or controller failure often '
                            'cannot be recovered in a repair shop; we explain the options after assessment.'},
            {'name': 'USB Flash Drive File Recovery', 'hours': 2,
             'description': 'Attempt to recover files from a USB flash drive that is detected but unreadable or was formatted.'},
            {'name': 'SD and Memory Card File Recovery', 'hours': 2,
             'description': 'Attempt to recover photos and files from SD and microSD cards that are still detected.'},
            {'name': 'External Hard Drive Data Recovery', 'hours': 3,
             'description': 'Attempt to recover files from an external hard drive or its enclosure. Recovery is not guaranteed.'},
            {'name': 'Data Backup and Restoration', 'hours': 2,
             'description': 'Back up your documents, photos and files to an external drive or new storage and restore them when needed.'},
            {'name': 'File Transfer Between Computers', 'hours': 2,
             'description': 'Copy your files, photos and documents from one computer to another.'},
            {'name': 'Windows User Profile Data Recovery', 'hours': 2,
             'description': 'Recover documents, desktop files and settings from a Windows user profile that no longer loads.'},
            {'name': 'Data Migration to a New Laptop or PC', 'hours': 3,
             'description': 'Move your files and settings to a new laptop or PC. Programs are reinstalled with your own licenses.'},
        ],
    },
    {
        'slug': 'hardware-repair', 'was': ['Hardware Repair'],
        'name': 'Hardware Repair and Troubleshooting', 'icon': 'fa-screwdriver-wrench',
        'description': 'Find and fix faults in laptops, desktop PCs and monitors.',
        'tagline': 'Diagnosis comes first: repairs and part replacements are confirmed and priced after it. '
                   'Not every motherboard or electronic component can be repaired.',
        'services': [
            {'name': 'Laptop Screen / LCD Replacement', 'was': ['Laptop Screen Replacement'], 'hours': 2, 'price': 3500,
             'description': 'Replace a cracked, dark or flickering laptop screen with a compatible panel for your model.'},
            {'name': 'Laptop Charging Port Repair', 'hours': 3,
             'description': 'Repair or replace a loose or damaged DC-in or USB-C charging port after diagnosis.'},
            {'name': 'Laptop Hinge Repair', 'hours': 2,
             'description': 'Repair or replace loose or broken laptop hinges and the mounts that hold them.'},
            {'name': 'Laptop Power Button Repair', 'hours': 2,
             'description': 'Repair or replace a laptop power button or its connecting board that no longer responds.'},
            {'name': 'Laptop Keyboard Repair', 'hours': 2,
             'description': 'Clean and fix individual stuck or unresponsive keys where possible, instead of replacing the keyboard.'},
            {'name': 'Desktop PC Power Supply Replacement', 'hours': 1,
             'description': 'Replace a failed desktop power supply with a unit of suitable wattage and connectors.'},
            {'name': 'Motherboard Troubleshooting', 'hours': 3,
             'description': 'Diagnose motherboard faults. Some can be repaired; others mean replacing the board, which we confirm and price first.'},
            {'name': 'RAM Detection and Hardware Fault Diagnosis', 'hours': 1,
             'description': 'Test memory and other components to find the cause of crashes, beeps or failure to start.'},
            {'name': 'CPU Cooling Fan Replacement', 'hours': 1,
             'description': 'Replace a noisy or failed CPU or laptop cooling fan with a compatible part.'},
            {'name': 'Overheating and Thermal Paste Replacement', 'hours': 2,
             'description': 'Clean dust from fans and vents and replace dried-out thermal paste to bring temperatures down.'},
            {'name': "Desktop PC Won't Turn On Diagnosis", 'hours': 1,
             'description': "Find out why a desktop PC won't power on: power supply, cables, switch, RAM or motherboard."},
            {'name': 'Laptop No-Power Troubleshooting', 'hours': 2,
             'description': 'Find out why a laptop shows no power or will not charge: adapter, battery, port or board.'},
            {'name': 'Desktop Monitor Display Troubleshooting', 'hours': 1,
             'description': 'Diagnose a monitor with no signal, lines or flicker, and whether the cable, graphics or panel is at fault.'},
            {'name': 'Loose Internal Cable and Connector Repair', 'hours': 1,
             'description': 'Reseat or replace loose internal cables and connectors causing intermittent faults.'},
        ],
    },
    {
        'slug': 'hardware-upgrade', 'was': ['Hardware Upgrade'],
        'name': 'Hardware Upgrade and Installation', 'icon': 'fa-microchip',
        'description': 'Upgrade parts or add new ones to make your computer faster or more capable.',
        'tagline': 'We check compatibility before any upgrade. Some laptops and all-in-one PCs have soldered or '
                   'non-upgradeable parts, so an upgrade is only confirmed after checking your model.',
        'services': [
            {'name': 'Desktop RAM Upgrade', 'hours': 1,
             'description': 'Add or replace desktop memory after checking the type, speed and slots your motherboard supports.'},
            {'name': 'Laptop RAM Upgrade', 'was': ['RAM Upgrade'], 'hours': 1, 'price': 2500,
             'description': 'Add or replace laptop memory where it is not soldered, after checking compatibility.'},
            {'name': 'SSD Installation', 'hours': 2, 'price': 3200,
             'description': 'Install a new SATA or NVMe SSD that your computer supports, ready for use.'},
            {'name': 'Graphics Card Installation or Upgrade', 'hours': 2,
             'description': 'Install a graphics card after checking power supply wattage, connectors and case space.'},
            {'name': 'Desktop Power Supply Upgrade', 'hours': 1,
             'description': 'Fit a higher-wattage or more efficient power supply to support new components.'},
            {'name': 'Compatible Processor Upgrade', 'hours': 2,
             'description': 'Upgrade a desktop CPU to one supported by your motherboard and BIOS, including cooler refit.'},
            {'name': 'CPU Cooler Installation', 'hours': 1,
             'description': 'Install an air or all-in-one liquid CPU cooler that fits your socket and case.'},
            {'name': 'Wi-Fi Adapter Installation', 'hours': 1,
             'description': 'Install a USB or internal Wi-Fi/Bluetooth adapter and its drivers.'},
            {'name': 'Desktop PC Component Assembly', 'hours': 4,
             'description': 'Assemble a desktop PC from compatible parts, with cable management and a first boot test.'},
            {'name': 'All-in-One PC Upgrade Assessment', 'hours': 1,
             'description': 'Check which parts of an all-in-one PC can actually be upgraded before any work is quoted.'},
            {'name': 'Dual Monitor Setup', 'hours': 1,
             'description': 'Connect and configure a second monitor, including cables and display settings.'},
        ],
    },
    {
        'slug': 'software-fix', 'was': ['Software Fix'],
        'name': 'Software Repair and Operating System Fixes', 'icon': 'fa-laptop-code',
        'description': 'Fix Windows problems, errors, viruses and slow computers.',
        'tagline': 'We only install licensed software: no pirated software or unauthorized product keys.',
        'services': [
            {'name': 'Windows Installation and Reinstallation', 'hours': 3,
             'description': 'Install or reinstall Windows with your own valid license, plus drivers and updates. Back up your files first.'},
            {'name': 'Windows Startup Repair', 'hours': 2,
             'description': 'Fix Windows that will not start or keeps looping at startup, without reinstalling where possible.'},
            {'name': 'Blue Screen Error Troubleshooting', 'hours': 2,
             'description': 'Find and fix the cause of blue screen (BSOD) errors: drivers, updates, memory or storage.'},
            {'name': 'Virus and Malware Removal', 'was': ['Virus Removal'], 'hours': 2, 'price': 1500,
             'description': 'Scan for and remove viruses, malware and unwanted programs, then set up protection.'},
            {'name': 'Driver Installation and Repair', 'hours': 1,
             'description': 'Install or repair device drivers for graphics, sound, network, printer and other hardware.'},
            {'name': 'System Freeze and Random Restart Troubleshooting', 'hours': 2,
             'description': 'Find the cause of freezing or random restarts, whether software, overheating or hardware.'},
            {'name': 'Slow Computer Optimization', 'was': ['System Optimization'], 'hours': 1, 'price': 1200,
             'description': 'Speed up a slow computer: startup programs, storage clean-up, updates and settings.'},
            {'name': 'Application Installation and Error Fixes', 'hours': 1,
             'description': 'Install your licensed applications and fix programs that crash or will not open.'},
            {'name': 'Windows Update Troubleshooting', 'hours': 2,
             'description': 'Fix Windows updates that fail, get stuck or keep rolling back.'},
            {'name': 'Operating System Boot Failure Repair', 'hours': 2,
             'description': 'Repair a computer that cannot find or load its operating system.'},
            {'name': 'Software Configuration and Setup', 'hours': 1,
             'description': 'Set up a new or reset computer: accounts, email, browsers and your licensed software.'},
            {'name': 'Printer Driver and Software Troubleshooting', 'hours': 1,
             'description': 'Install printer and scanner drivers and fix printing or scanning errors.'},
            {'name': 'File System Error Checking', 'hours': 1,
             'description': 'Check and repair drive file-system errors that cause missing or unreadable files.'},
            {'name': 'Operating System and Driver Updates', 'hours': 1,
             'description': 'Bring Windows and device drivers up to date safely.'},
        ],
    },
    {
        'slug': 'storage-upgrade', 'was': ['Storage Upgrade'],
        'name': 'Storage Upgrade', 'icon': 'fa-hdd',
        'description': 'Faster or bigger storage, with your system and files moved across.',
        'tagline': 'Before a drive is replaced we back up or clone your data whenever the old drive can still be read.',
        'services': [
            {'name': 'HDD-to-SSD Migration', 'was': ['HDD to SSD Migration'], 'hours': 2, 'price': 3200,
             'description': 'Replace a hard drive with an SSD and move your Windows installation and files across.'},
            {'name': 'Hard Drive Replacement', 'hours': 2,
             'description': 'Replace a failing or full hard drive, with your data copied over where the old drive is readable.'},
            {'name': 'SSD Replacement or Capacity Upgrade', 'hours': 2,
             'description': 'Replace an SSD with a larger or healthier one and move your system across.'},
            {'name': 'Additional Storage Installation', 'hours': 1,
             'description': 'Add a second SSD or hard drive where your computer has a free slot or bay.'},
            {'name': 'Operating System Cloning', 'hours': 2,
             'description': 'Clone your current Windows installation to a new drive so everything works as before.'},
            {'name': 'Storage Health Assessment', 'hours': 1,
             'description': 'Check the health of your HDD or SSD and warn you before it fails.'},
        ],
    },
]


def sync_service_catalog(db, ServiceCategory, Service):
    """Apply CATALOG (see module docstring). Commits. Returns a list of changes."""
    changes = []
    for order, spec in enumerate(CATALOG, start=1):
        names = [spec['name']] + spec.get('was', [])
        cat = ServiceCategory.query.filter_by(slug=spec['slug']).first() or \
            ServiceCategory.query.filter(ServiceCategory.name.in_(names)).first()
        if cat is None:
            cat = ServiceCategory(slug=spec['slug'], is_active=True)
            db.session.add(cat)
            changes.append(f'add category {spec["name"]}')
        elif cat.name != spec['name']:
            changes.append(f'rename category {cat.name!r} -> {spec["name"]!r}')
        cat.name, cat.icon = spec['name'], spec['icon']
        cat.description, cat.tagline, cat.display_order = spec['description'], spec['tagline'], order
        db.session.flush()

        for svc in spec['services']:
            wanted = [svc['name']] + svc.get('was', [])
            match = None
            for n in wanted:                       # prefer the current name, then old names
                match = Service.query.filter(func.lower(Service.name) == n.lower()).first()
                if match:
                    break
            if match is None:
                db.session.add(Service(category_id=cat.id, name=svc['name'], description=svc['description'],
                                       price=svc.get('price', 0), estimated_hours=svc['hours'], is_active=True))
                changes.append(f'add service {svc["name"]}')
                continue
            if match.name != svc['name'] or match.category_id != cat.id:
                changes.append(f'update service {match.name!r} -> {svc["name"]!r}')
            match.name, match.description, match.category_id = svc['name'], svc['description'], cat.id
    db.session.commit()
    return changes
