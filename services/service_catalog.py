"""DEVTech's service catalog.

sync_service_catalog() brings the service_categories / services tables in line
with CATALOG without duplicating anything:
  - categories are found by slug (or old name) and renamed in place, so ids,
    slugs/URLs and bookings stay as they are;
  - services are found by name (case-insensitive) or by an old name (`was`);
  - services that don't exist yet are added with their starting price; a service
    still priced 0 gets its starting price, a price set in Admin is kept;
  - each service's device types come from here (which devices it is for);
  - RETIRED services are hidden (not deleted, so past bookings keep them).

replace=True makes the database match CATALOG exactly: every listed service
gets the listed starting price, hours and description and is shown again;
every service and category that is not listed is hidden (never deleted, so old
bookings still show what was booked). Use it when the shop's service list is
replaced: `flask --app app sync-service-catalog --replace`.

It is safe to run more than once. Used by init_db() for a new database and by
`flask --app app sync-service-catalog` for an existing one. It does not run on
every start, so later edits made in Admin > Services are not overwritten.
"""
from sqlalchemy import func

# price = starting price in pesos for the work. Replacement parts depend on the
# model and are quoted before the work starts.
# hours = typical time for a straightforward job; admins can change it.
# devices = the device types a service is for (see DEVICE_TYPES).
DEVICE_TYPES = {'laptop': 'Laptop', 'desktop': 'Desktop PC', 'tablet': 'Tablet', 'smartphone': 'Smartphone',
                'monitor': 'Monitor', 'storage': 'Storage Device'}

L, D, T, S, M, X = 'laptop', 'desktop', 'tablet', 'smartphone', 'monitor', 'storage'
PC = [L, D]

# Hidden even without replace=True (the shop no longer offers them).
RETIRED = ['All-in-One PC Upgrade Assessment', 'Printer Driver and Software Troubleshooting']


def _svc(name, price, hours, devices, description, was=()):
    return {'name': name, 'price': price, 'hours': hours, 'devices': list(devices),
            'description': description, 'was': list(was)}


CATALOG = [
    {
        'slug': 'accessory-replacement', 'was': ['Accessory Replacement'],
        'name': 'Accessory Replacement Services', 'icon': 'fa-plug',
        'description': 'Replace worn, broken or faulty parts in laptops, desktops, tablets, phones, monitors and drives.',
        'tagline': 'Prices are starting prices for the work. The replacement part depends on your model and is '
                   'quoted before we start.',
        'services': [
            # Laptop
            _svc('Laptop Keyboard Replacement', 800, 2, [L], 'Replace a keyboard with missing, stuck or dead keys with a part made for your model.'),
            _svc('Laptop LCD / LED Screen Replacement', 1000, 2, [L], 'Replace a cracked, dark or line-filled laptop screen with a panel matched to your model.',
                 was=['Laptop Screen / LCD Replacement']),
            _svc('Laptop Battery Replacement', 500, 1, [L], 'Replace a battery that no longer holds a charge or has started to swell.'),
            _svc('Laptop Charging Port Replacement', 900, 2, [L], 'Replace a loose or burnt DC jack or USB-C port so the laptop charges reliably again.',
                 was=['Laptop Charging Port Repair']),
            _svc('Laptop Cooling Fan Replacement', 700, 2, [L], 'Replace a noisy, slow or stopped cooling fan and clear the heatsink vents.'),
            _svc('Laptop Hinges Replacement', 900, 2, [L], 'Replace broken or stiff hinges and check the screen cable and hinge mounts in the casing.'),
            _svc('Laptop Speaker Replacement', 600, 2, [L], 'Replace crackling or silent internal speakers once audio drivers have been ruled out.'),
            _svc('Laptop Touchpad Replacement', 800, 2, [L], 'Replace a touchpad that no longer clicks or tracks, after checking it is not a driver problem.'),
            _svc('Laptop Webcam Replacement', 700, 2, [L], 'Replace a built-in camera that shows no picture or a blurry, dark image.'),
            _svc('Laptop Wi-Fi Card Replacement', 600, 1, [L], 'Replace a failed wireless card and install its drivers so Wi-Fi and Bluetooth work again.'),
            _svc('Laptop Power Button Replacement', 600, 2, [L], 'Replace a power button or its board when pressing it does nothing or only works sometimes.'),
            _svc('Laptop Screen Cable Replacement', 800, 2, [L], 'Replace a worn display cable that makes the screen flicker or go blank when the lid moves.'),
            # Desktop PC
            _svc('Power Supply Unit (PSU) Replacement', 500, 1, [D], 'Replace a dead or failing power supply with a unit of the right wattage and connectors.',
                 was=['Desktop PC Power Supply Replacement']),
            _svc('Motherboard Replacement', 1500, 3, [D], 'Move your parts to a compatible motherboard and set it up so Windows starts as before.'),
            _svc('Desktop CPU Cooler Replacement', 500, 1, [D], 'Replace a noisy or failed CPU cooler and apply fresh thermal paste.',
                 was=['CPU Cooling Fan Replacement']),
            _svc('Case Fan Replacement', 300, 1, [D], 'Replace a rattling or stopped case fan and check the airflow direction.'),
            _svc('Graphics Card Replacement', 500, 1, [D], 'Swap a faulty graphics card for a compatible one and install its drivers.'),
            _svc('RAM Replacement', 300, 1, [D], 'Replace a faulty memory stick found by a memory test, matched to your motherboard.'),
            _svc('CMOS Battery Replacement', 250, 1, [D], 'Replace the small board battery when the clock and BIOS settings reset after every shutdown.'),
            _svc('Desktop Power Button Replacement', 400, 1, [D], 'Replace or rewire a front power button that no longer starts the computer.'),
            _svc('SATA Cable Replacement', 250, 1, [D], 'Replace a damaged SATA data cable that makes a drive disappear or disconnect.'),
            _svc('Desktop Front Panel Port Repair', 600, 2, [D], 'Repair loose or dead front USB and audio ports and their cables to the motherboard.'),
            _svc('Desktop Case Replacement / Transfer', 1200, 3, [D], 'Move all your parts into a new case, with tidy cabling and working front ports.'),
            _svc('Internal Power Cable Replacement', 350, 1, [D], 'Replace melted or damaged internal power cables and adapters to drives and boards.'),
            # Tablet
            _svc('Tablet LCD Screen Replacement', 1200, 2, [T], 'Replace a tablet display that is black, bleeding or showing lines.',
                 was=['Tablet Screen / Digitizer Replacement']),
            _svc('Tablet Touchscreen / Digitizer Replacement', 1000, 2, [T], 'Replace cracked touch glass or a digitizer that no longer responds to touch.'),
            _svc('Tablet Battery Replacement', 800, 2, [T], 'Replace a tablet battery that drains quickly, swells or shuts off at a high percentage.'),
            _svc('Tablet Charging Port Replacement', 700, 2, [T], 'Replace a loose or damaged charging port so the tablet charges and syncs again.'),
            _svc('Tablet Speaker Replacement', 600, 2, [T], 'Replace quiet, distorted or silent tablet speakers.'),
            _svc('Tablet Microphone Replacement', 600, 2, [T], 'Replace a microphone that others can no longer hear during calls or recordings.'),
            _svc('Tablet Camera Replacement', 700, 2, [T], 'Replace a front or rear camera that is blurry, black or will not open.'),
            _svc('Tablet Power Button Replacement', 600, 2, [T], 'Replace a stuck or unresponsive power button or its flex cable.'),
            _svc('Tablet Volume Button Replacement', 600, 2, [T], 'Replace volume buttons that are stuck, loose or do nothing.'),
            _svc('Tablet Flex Cable Replacement', 800, 2, [T], 'Replace a torn internal flex cable that cuts the display, buttons or charging.'),
            # Smartphone
            _svc('Smartphone LCD / OLED Screen Replacement', 900, 2, [S], 'Replace a broken, black or line-filled phone display with a part for your model.',
                 was=['Smartphone Screen Replacement']),
            _svc('Smartphone Touchscreen Replacement', 700, 2, [S], 'Replace cracked touch glass or a touchscreen that registers wrong or no taps.'),
            _svc('Smartphone Battery Replacement', 500, 1, [S], 'Replace a phone battery that drains fast, swells or shuts off early.',
                 was=['Phone or Tablet Battery Replacement']),
            _svc('Charging Port Replacement', 500, 1, [S], 'Replace a loose, dirty or damaged phone charging port so it charges and connects again.',
                 was=['Phone or Tablet Charging Port Repair']),
            _svc('Front Camera Replacement', 500, 1, [S], 'Replace a front (selfie) camera that is blurry, black or fails to open.'),
            _svc('Rear Camera Replacement', 600, 1, [S], 'Replace a rear camera module that will not focus, shakes or shows a black screen.'),
            _svc('Loudspeaker Replacement', 450, 1, [S], 'Replace a phone loudspeaker that crackles or makes no sound for ringtones and media.'),
            _svc('Earpiece Speaker Replacement', 450, 1, [S], 'Replace the earpiece when you can no longer hear callers clearly.'),
            _svc('Microphone Replacement', 450, 1, [S], 'Replace a phone microphone when callers cannot hear you.'),
            _svc('Power Button Replacement', 450, 1, [S], 'Replace a stuck or unresponsive phone power button or its flex cable.'),
            _svc('Volume Button Replacement', 450, 1, [S], 'Replace phone volume buttons that are stuck or do nothing.'),
            _svc('SIM Card Tray Replacement', 250, 1, [S], 'Replace a lost, bent or broken SIM tray so the SIM card seats properly.'),
            _svc('Back Cover Replacement', 400, 1, [S], 'Replace a cracked or loose back glass or cover and reseal it.'),
            _svc('Fingerprint Sensor Replacement', 600, 1, [S], 'Replace a fingerprint sensor that no longer reads, where the part can be paired to your phone.'),
            # Monitor
            _svc('Monitor LCD Panel Replacement', 1500, 3, [M, D], 'Replace a cracked or damaged monitor panel with one that fits your model.',
                 was=['Desktop Monitor Replacement']),
            _svc('Monitor Power Supply Board Replacement', 900, 2, [M, D], 'Replace the power board when the monitor will not turn on or clicks on and off.'),
            _svc('Monitor Mainboard Replacement', 1000, 2, [M, D], 'Replace the main logic board when the monitor shows no signal on every input.'),
            _svc('Monitor Backlight Repair', 900, 3, [M, D], 'Repair LED backlight strips when the picture is very dark or only visible with a torch.'),
            _svc('Monitor HDMI Port Replacement', 600, 2, [M, D], 'Replace a loose or dead HDMI input on the monitor.'),
            _svc('Monitor VGA Port Replacement', 500, 2, [M, D], 'Replace a bent or dead VGA input on the monitor.'),
            _svc('Monitor Display Cable Replacement', 300, 1, [M, D], 'Replace a faulty HDMI, DisplayPort or VGA cable between the computer and monitor.'),
            _svc('Monitor Control Button Replacement', 500, 2, [M, D], 'Replace monitor menu and power buttons that are stuck or unresponsive.'),
            _svc('Monitor Power Port Replacement', 500, 2, [M, D], 'Replace a loose or burnt power input on the monitor.'),
            # Storage
            _svc('Laptop HDD Replacement', 400, 2, [L], 'Replace a failing laptop hard drive, copying your files across while the old drive is readable.',
                 was=['Hard Drive Replacement']),
            _svc('Laptop SSD Replacement / Installation', 400, 2, [L], 'Fit a new SSD in your laptop and move your system across when the old drive can still be read.'),
            _svc('Desktop HDD Replacement', 350, 1, [D], 'Replace a failing desktop hard drive, copying your files across while the old drive is readable.'),
            _svc('Desktop SSD Replacement / Installation', 350, 1, [D], 'Fit a new SSD in your desktop PC and move your system across if needed.'),
            _svc('M.2 NVMe SSD Installation', 400, 1, PC, 'Install an M.2 NVMe SSD in a free slot, after checking your board supports it.'),
            _svc('External HDD Enclosure Replacement', 300, 1, [X], 'Move a working drive into a new USB enclosure when the old case or its board has failed.'),
            _svc('SATA Connector Replacement', 600, 2, [L, D, X], 'Replace a cracked or loose SATA connector on a drive or its adapter.'),
            _svc('Storage Cable Replacement', 250, 1, [D, X], 'Replace a worn USB, SATA or power cable that makes a drive disconnect.'),
            _svc('External Storage Port Repair', 600, 2, [X], 'Repair a loose or broken USB port on an external hard drive or SSD.'),
        ],
    },
    {
        'slug': 'data-recovery', 'was': ['Data Recovery', 'Data Recovery and Backup'],
        'name': 'Data Recovery and Backup Services', 'icon': 'fa-database',
        'description': 'Recover lost files, back up your data and move it to a new device.',
        'tagline': 'Data recovery is not guaranteed. Physically damaged, encrypted or failed drives may need a specialist '
                   'recovery laboratory; we tell you what is possible after diagnosis.',
        'services': [
            _svc('Basic Deleted File Recovery', 800, 2, [L, D, X], 'Attempt to recover recently deleted files from a working drive. Stop using the drive '
                 'to improve the chances. Recovery is not guaranteed.', was=['Deleted File Recovery']),
            _svc('Formatted Drive Data Recovery Assessment', 500, 1, [L, D, X], 'Check what can still be recovered from a drive that was formatted or reset.'),
            _svc('HDD Data Recovery', 2500, 4, [L, D, X], 'Recover files from a hard drive that still spins and is detected. A drive with physical '
                 'damage may need a specialist laboratory. Recovery is not guaranteed.', was=['HDD File Recovery']),
            _svc('SSD Data Recovery', 3000, 4, [L, D, X], 'Attempt to read files from a failing SSD. Controller failures often cannot be recovered '
                 'in a repair shop; we explain the options first.', was=['SSD Data Recovery Assessment']),
            _svc('USB Flash Drive Data Recovery', 1200, 2, [X], 'Attempt to recover files from a USB flash drive that is detected but unreadable or was formatted.',
                 was=['USB Flash Drive File Recovery']),
            _svc('Memory Card Data Recovery', 1200, 2, [X], 'Attempt to recover photos and files from SD and microSD cards that are still detected.',
                 was=['SD and Memory Card File Recovery']),
            _svc('External Hard Drive Data Recovery', 2500, 4, [X], 'Attempt to recover files from an external hard drive or its enclosure. Recovery is not guaranteed.'),
            _svc('Corrupted File System Recovery', 1500, 3, [L, D, X], 'Recover files from a drive that asks to be formatted or shows as RAW.'),
            _svc('Partition Recovery', 1500, 3, [L, D, X], 'Find and restore a deleted or lost partition and the files on it.'),
            _svc('Operating System File Recovery', 1000, 2, PC, 'Copy your documents, photos and desktop files off a computer whose Windows no longer starts.'),
            _svc('Basic Personal File Backup', 400, 1, [L, D, T, S, X], 'Copy your documents, photos and videos to a drive or cloud account you provide.',
                 was=['Data Backup and Restoration']),
            _svc('Full Storage Device Backup', 800, 2, [L, D, X], 'Make a complete copy of a drive, including the system, so it can be restored later.'),
            _svc('Data Transfer to New Storage Device', 600, 2, [L, D, X], 'Move all your files from an old drive to a new one and check that they open.'),
            _svc('Laptop-to-Laptop Data Migration', 800, 2, [L], 'Move your files, browser bookmarks and settings from your old laptop to the new one.'),
            _svc('Smartphone Data Backup', 400, 1, [S], 'Back up contacts, photos, messages and app data before a repair or reset.'),
            _svc('Tablet Data Backup', 400, 1, [T], 'Back up photos, documents and app data from your tablet before a repair or reset.'),
        ],
    },
    {
        'slug': 'hardware-repair', 'was': ['Hardware Repair'],
        'name': 'Hardware Repair Services', 'icon': 'fa-microchip',
        'description': 'Find and fix the fault behind no power, overheating, liquid damage, broken ports and display problems.',
        'tagline': 'Every repair starts with a diagnosis. If the cost goes above the starting price we ask you first.',
        'services': [
            _svc('Laptop Motherboard Inspection', 500, 2, [L], 'Check the board, memory, drive and power circuit to find the fault behind a problem you cannot pin down.',
                 was=['RAM Detection and Hardware Fault Diagnosis']),
            _svc('Desktop Motherboard Inspection', 400, 2, [D], 'Check the board, memory, power supply and drives to find the fault behind random crashes or no start.',
                 was=['Motherboard Troubleshooting']),
            _svc('Laptop No Power Repair', 800, 3, [L], 'Trace why a laptop shows no lights or fan at all: adapter, battery, power circuit or board.',
                 was=['Laptop No-Power Troubleshooting']),
            _svc('Desktop No Power Repair', 600, 2, [D], 'Find why a desktop PC will not start: power supply, button, board or short circuit.',
                 was=["Desktop PC Won't Turn On Diagnosis"]),
            _svc('Laptop Overheating Repair', 700, 2, [L], 'Stop a laptop from overheating or shutting down: clean, repaste and check the fan and heatsink.',
                 was=['Overheating and Thermal Paste Replacement']),
            _svc('Desktop Overheating Repair', 500, 2, [D], 'Fix high temperatures and sudden shutdowns: dust, coolers, paste and airflow.'),
            _svc('Laptop Fan Cleaning and Repair', 500, 2, [L], 'Clean and lubricate a loud or slow laptop fan, or replace it if it is worn out.'),
            _svc('Desktop Fan Cleaning and Repair', 350, 1, [D], 'Clean noisy CPU, case and power supply fans and replace any that are failing.'),
            _svc('Laptop Charging Problem Repair', 700, 2, [L], 'Find why a laptop will not charge: adapter, port, battery or charging circuit.'),
            _svc('Desktop Power Problem Repair', 500, 2, [D], 'Fix a desktop that restarts, cuts out or will not stay on, from the power supply to the board.'),
            _svc('Motherboard Component-Level Repair', 2000, 6, PC, 'Replace failed chips, capacitors or connectors on the board instead of replacing the whole board.'),
            _svc('Laptop Liquid Damage Assessment', 500, 2, [L], 'Open and check a laptop after a spill to see what was damaged. Switch it off and bring it in fast.',
                 was=['Water Damage Cleaning and Assessment']),
            _svc('Liquid Damage Cleaning and Repair', 1500, 4, PC, 'Clean corrosion from the board and replace damaged parts after a spill.'),
            _svc('Broken Laptop Hinge Repair', 800, 2, [L], 'Repair cracked hinge mounts and casing so the lid opens and closes safely again.'),
            _svc('Damaged USB Port Repair', 600, 2, PC, 'Repair or replace loose, bent or dead USB ports.'),
            _svc('Damaged HDMI Port Repair', 800, 2, PC, 'Repair or replace a loose or dead HDMI output.'),
            _svc('Laptop Display Problem Repair', 600, 2, [L], 'Find why the laptop screen is black, dim or flickering: cable, backlight, panel or graphics.',
                 was=['Desktop Monitor Display Troubleshooting']),
            _svc('Desktop Display Output Repair', 500, 2, [D], 'Fix a desktop PC that shows no picture: graphics card, ports, cables or settings.'),
            _svc('Monitor Flickering Repair', 700, 2, [M, D], 'Find and fix the cause of a monitor that flickers, shows lines or changes brightness.'),
            _svc('Monitor No Display Repair', 700, 2, [M, D], 'Fix a monitor that powers on but shows nothing: board, backlight or inputs.'),
        ],
    },
    {
        'slug': 'hardware-upgrade', 'was': ['Hardware Upgrade'],
        'name': 'Hardware Upgrade and Installation', 'icon': 'fa-memory',
        'description': 'More memory, faster storage, better cooling, new parts and complete PC builds.',
        'tagline': 'We check that a part is compatible before you buy it. Prices are for the work; parts are quoted separately.',
        'services': [
            _svc('Laptop RAM Upgrade', 300, 1, [L], 'Add or replace memory in a laptop with free or upgradable slots, matched to what it supports.'),
            _svc('Desktop RAM Upgrade', 250, 1, [D], 'Add memory to a desktop PC, matched to your motherboard and run in the right slots.'),
            _svc('Laptop SSD Upgrade', 500, 2, [L], 'Replace a slow laptop hard drive with an SSD and move your Windows and files across.',
                 was=['HDD-to-SSD Migration']),
            _svc('Desktop SSD Upgrade', 450, 2, [D], 'Add an SSD to a desktop PC and move Windows to it for faster start-up.'),
            _svc('HDD Installation', 350, 1, PC, 'Install an extra hard drive for storage and set it up in Windows.'),
            _svc('NVMe SSD Installation', 400, 1, PC, 'Install an NVMe SSD, set it up in Windows, and move your system to it if you want.'),
            _svc('Graphics Card Installation', 500, 1, [D], 'Install a new graphics card, check the power supply can run it and install drivers.'),
            _svc('Power Supply Upgrade', 500, 1, [D], 'Fit a higher-wattage power supply for new parts, with tidy cabling.'),
            _svc('CPU Cooler Installation', 500, 1, [D], 'Install an aftermarket air or liquid CPU cooler with fresh thermal paste.'),
            _svc('Desktop Motherboard Installation', 1500, 3, [D], 'Install a new motherboard and move your processor, memory and drives to it.'),
            _svc('Laptop Thermal Paste Replacement', 500, 1, [L], 'Replace dried thermal paste on the processor and graphics chip to lower temperatures.'),
            _svc('Desktop Thermal Paste Replacement', 350, 1, [D], 'Replace dried thermal paste on the processor for cooler, quieter running.'),
            _svc('Laptop Internal Cleaning', 500, 1, [L], 'Open the laptop and clean dust from the fan, heatsink and vents.'),
            _svc('Desktop Full Internal Cleaning', 400, 1, [D], 'Clean dust from every fan, filter, heatsink and the power supply.'),
            _svc('Laptop Operating Memory Upgrade Assessment', 200, 1, [L], 'Check how much memory your laptop supports, which slots are free and whether more will speed it up.'),
            _svc('Desktop Cable Management', 400, 1, [D], 'Route and tie the cables inside your PC for better airflow and easier upgrades.'),
            _svc('Additional Case Fan Installation', 300, 1, [D], 'Add case fans for better airflow and connect them to the board or a hub.'),
            _svc('PC Component Compatibility Assessment', 300, 1, [D], 'Check that the parts you plan to buy work together before you pay for them.'),
            _svc('Complete Desktop PC Assembly', 1500, 4, [D], 'Build a desktop PC from your parts, install Windows and drivers, and test it under load.'),
            _svc('Desktop PC Component Upgrade', 500, 2, [D], 'Install a new processor, board or other part and make sure everything still works together.'),
        ],
    },
    {
        'slug': 'mobile-repair', 'was': ['Smartphone and Tablet Repair'],
        'name': 'Smartphone and Tablet Repair', 'icon': 'fa-mobile-screen',
        'description': 'Charging, power, boot, water, sound, camera, signal and software problems on phones and tablets.',
        'tagline': 'Back up your phone or tablet first if you can. Parts are quoted for your exact model before we start.',
        'services': [
            _svc('Smartphone Not Charging Repair', 500, 2, [S], 'Find why the phone will not charge: cable, port, battery or charging chip.'),
            _svc('Smartphone Not Turning On Repair', 700, 2, [S], 'Find why the phone stays dead: battery, button, power circuit or software.'),
            _svc('Smartphone Boot Loop Repair', 600, 2, [S], 'Fix a phone stuck on the logo or restarting, keeping your data where possible.',
                 was=['Phone or Tablet Software Repair']),
            _svc('Smartphone Overheating Assessment', 300, 1, [S], 'Check why the phone runs hot: battery, charging, apps or a damaged part.'),
            _svc('Smartphone Water Damage Assessment', 300, 1, [S], 'Open and check a phone after water exposure. Do not charge it; bring it in quickly.'),
            _svc('Smartphone Water Damage Cleaning', 800, 3, [S], 'Clean corrosion from the board and connectors after water damage.'),
            _svc('Smartphone Speaker Problem Repair', 450, 1, [S], 'Fix quiet, distorted or silent speakers, from blocked grilles to a failed part.',
                 was=['Speaker and Microphone Repair']),
            _svc('Smartphone Microphone Problem Repair', 450, 1, [S], 'Fix a phone when callers cannot hear you or voice recordings are silent.'),
            _svc('Smartphone Camera Problem Repair', 500, 1, [S], 'Fix a camera that is blurry, black, shaking or will not open.'),
            _svc('Smartphone Network / Signal Problem Assessment', 400, 1, [S], 'Check why the phone has no signal or no SIM: tray, antenna, settings or board.'),
            _svc('Smartphone Wi-Fi Connectivity Repair', 500, 2, [S], 'Fix a phone that will not turn on Wi-Fi, drops connection or cannot find networks.'),
            _svc('Smartphone Software Crash Repair', 500, 2, [S], 'Fix apps or the system that keep crashing or freezing, with your data backed up first.'),
            _svc('Smartphone Touchscreen Problem Assessment', 300, 1, [S], 'Check why the touchscreen ignores taps or touches by itself.'),
            _svc('Smartphone Button Repair', 450, 1, [S], 'Fix power, volume or home buttons that are stuck or do nothing.'),
            _svc('Tablet Not Charging Repair', 600, 2, [T], 'Find why the tablet will not charge: cable, port, battery or charging circuit.'),
            _svc('Tablet Not Turning On Repair', 800, 2, [T], 'Find why the tablet stays dead: battery, button, power circuit or software.'),
            _svc('Tablet Boot Loop Repair', 700, 2, [T], 'Fix a tablet stuck on the logo or restarting, keeping your data where possible.'),
            _svc('Tablet Speaker and Microphone Repair', 600, 2, [T], 'Fix tablet speakers or microphones that are silent, quiet or distorted.'),
            _svc('Tablet Wi-Fi Connectivity Repair', 600, 2, [T], 'Fix a tablet that will not connect to or keeps dropping Wi-Fi.'),
            _svc('Tablet Software Problem Repair', 600, 2, [T], 'Fix apps or the system that crash, freeze or will not update.'),
            _svc('Tablet Water Damage Cleaning', 900, 3, [T], 'Clean corrosion from the board and connectors after water damage.'),
            _svc('Tablet Performance Optimization', 400, 1, [T], 'Speed up a slow tablet: storage clean-up, updates and removing what slows it down.'),
        ],
    },
    {
        'slug': 'software-fix', 'was': ['Software Fix'],
        'name': 'Software Repair and Operating System Fixes', 'icon': 'fa-laptop-code',
        'description': 'Windows installation and repair, drivers, viruses, slow computers, apps and network settings.',
        'tagline': 'We back up your files before reinstalling or repairing Windows whenever the drive can be read. '
                   'Bring your own licence keys for paid software.',
        'services': [
            _svc('Windows Operating System Installation', 500, 2, PC, 'Install Windows on a new or empty drive, with drivers and updates.'),
            _svc('Windows Reinstallation', 600, 2, PC, 'Back up your files, reinstall Windows cleanly and put your files back.'),
            _svc('Windows Startup Repair', 500, 2, PC, 'Repair Windows when it starts very slowly, hangs at the logo or shows repair screens.'),
            _svc('Windows Boot Failure Troubleshooting', 500, 2, PC, 'Find why the computer turns on but Windows will not start, and fix it.',
                 was=['Operating System Boot Failure Repair']),
            _svc('Blue Screen Error Troubleshooting', 500, 2, PC, 'Find the cause of blue screen errors from crash logs and memory and drive tests, then fix it.'),
            _svc('Windows Update Error Repair', 400, 2, PC, 'Fix updates that fail, roll back or get stuck installing.',
                 was=['Windows Update Troubleshooting']),
            _svc('Driver Installation and Configuration', 300, 1, PC, 'Install the right drivers for graphics, sound, Wi-Fi, printers and other devices.',
                 was=['Driver Installation and Repair']),
            _svc('Driver Compatibility Troubleshooting', 400, 1, PC, 'Fix devices that stopped working after an update or show errors in Device Manager.'),
            _svc('Virus and Malware Removal', 500, 2, PC, 'Remove viruses, ransomware leftovers and other malware, then secure the computer.'),
            _svc('Spyware and Adware Removal', 400, 1, PC, 'Remove pop-ups, browser hijackers and unwanted programs that came bundled with downloads.'),
            _svc('System Performance Optimization', 400, 1, PC, 'Speed up a slow computer: start-up programs, storage clean-up, updates and settings.',
                 was=['Slow Computer Optimization']),
            _svc('Software Installation and Configuration', 300, 1, PC, 'Install and set up the programs you need, using your own licence keys.'),
            _svc('Application Error Troubleshooting', 350, 1, PC, 'Fix a program that crashes, will not open or shows error messages.',
                 was=['Application Installation and Error Fixes']),
            _svc('Windows Activation Troubleshooting', 300, 1, PC, 'Fix activation errors with your existing genuine licence.'),
            _svc('Corrupted System File Repair', 450, 2, PC, 'Repair damaged Windows system files that cause errors, freezes or missing features.',
                 was=['System Freeze and Random Restart Troubleshooting']),
            _svc('Operating System Recovery', 600, 2, PC, 'Restore Windows from a recovery partition or image when it can no longer be repaired.'),
            _svc('Startup and Boot Configuration Repair', 450, 2, PC, 'Repair boot settings and the boot record after a failed update, a new drive or dual boot.'),
            _svc('Network and Internet Configuration', 350, 1, PC, 'Set up Wi-Fi, wired network, sharing and printers on your home or office network.'),
            _svc('Wi-Fi Driver and Connectivity Troubleshooting', 350, 1, PC, 'Fix Wi-Fi that will not turn on, keeps dropping or shows no networks.',
                 was=['Wi-Fi Adapter Installation']),
            _svc('System Restore and Recovery Point Setup', 300, 1, PC, 'Turn on System Restore and make a recovery drive so problems can be undone later.'),
            _svc('Basic Application Setup', 250, 1, PC, 'Set up everyday apps: browser, office suite, PDF reader, video calls and antivirus.'),
            _svc('File Association and Default App Repair', 250, 1, PC, 'Make files open with the right programs again and set your default apps.'),
        ],
    },
]


def _find_service(Service, names):
    """The first service whose name matches one of names (case-insensitive), in order."""
    for n in names:
        match = Service.query.filter(func.lower(Service.name) == n.lower()).first()
        if match:
            return match
    return None


def sync_service_catalog(db, ServiceCategory, Service, replace=False):
    """Apply CATALOG (see module docstring). Commits. Returns a list of changes."""
    changes = []
    kept_service_ids, kept_category_ids = set(), set()
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
        if replace and not cat.is_active:
            cat.is_active = True
            changes.append(f'show category {spec["name"]}')
        cat.name, cat.icon = spec['name'], spec['icon']
        cat.description, cat.tagline, cat.display_order = spec['description'], spec['tagline'], order
        db.session.flush()
        kept_category_ids.add(cat.id)

        for svc in spec['services']:
            # The current name first; an old name only if that record isn't
            # already taken by another listed service.
            match = _find_service(Service, [svc['name']])
            if match is None:
                old = _find_service(Service, svc['was'])
                if old is not None and old.id not in kept_service_ids:
                    match = old
            devices = ','.join(svc['devices'])
            if match is None:
                match = Service(category_id=cat.id, name=svc['name'], description=svc['description'],
                                price=svc['price'], estimated_hours=svc['hours'], is_active=True,
                                device_types=devices)
                db.session.add(match)
                db.session.flush()
                kept_service_ids.add(match.id)
                changes.append(f'add service {svc["name"]}')
                continue
            kept_service_ids.add(match.id)
            if match.name != svc['name'] or match.category_id != cat.id:
                changes.append(f'update service {match.name!r} -> {svc["name"]!r}')
            if replace:
                if match.price != svc['price'] or match.estimated_hours != svc['hours'] or not match.is_active:
                    changes.append(f'set {svc["name"]}: from {svc["price"]}, {svc["hours"]} h')
                match.price, match.estimated_hours, match.is_active = svc['price'], svc['hours'], True
            elif not match.price:
                changes.append(f'starting price {svc["name"]}: {svc["price"]}')
                match.price = svc['price']
            if (match.device_types or '') != devices:
                changes.append(f'devices {svc["name"]}: {devices}')
            match.name, match.description, match.category_id = svc['name'], svc['description'], cat.id
            match.device_types = devices

    if replace:
        # Everything not on the list is hidden (kept for past bookings).
        for old in Service.query.filter(Service.is_active.is_(True)).all():
            if old.id not in kept_service_ids:
                old.is_active = False
                changes.append(f'hide service {old.name}')
        for old in ServiceCategory.query.filter(ServiceCategory.is_active.is_(True)).all():
            if old.id not in kept_category_ids:
                old.is_active = False
                changes.append(f'hide category {old.name}')
    else:
        for name in RETIRED:
            old = Service.query.filter(func.lower(Service.name) == name.lower(), Service.is_active.is_(True)).first()
            if old:
                old.is_active = False
                changes.append(f'retire service {name}')
    db.session.commit()
    return changes
