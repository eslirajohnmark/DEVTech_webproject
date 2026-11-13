"""Troubleshooting assistant: matches a customer's own description of a problem
against a knowledge base of specific, common faults per device, and is honest
about how sure it is.

  * is_specific(text) refuses descriptions that are random letters or too vague
    to act on (also used by the booking form);
  * diagnose(device, category, text) returns the most likely problem, the steps
    a customer can safely try, how confident the match is and why, and which
    service to book.

Confidence is earned, never assumed:
  high    - two or more symptoms of one known problem, or one clear symptom that
            agrees with the problem type the customer picked;
  medium  - one symptom only, or it points to a different problem type;
  low     - nothing recognisable, or the customer says they don't know the
            cause. Low confidence never shows do-it-yourself steps: it sends the
            customer to a technician.
English and common Filipino / Taglish phrasing are understood.
"""
import re

DEVICES = {
    'laptop': 'Laptop', 'desktop': 'Desktop PC', 'tablet': 'Tablet', 'smartphone': 'Smartphone',
}
PC = {'laptop', 'desktop'}
MOBILE = {'tablet', 'smartphone'}
ALL = PC | MOBILE

CATEGORIES = {
    'startup': 'Won\'t turn on or start',
    'screen': 'Screen or display',
    'battery': 'Battery or charging',
    'slow': 'Slow or freezing',
    'software': 'Errors, crashes or apps',
    'virus': 'Virus, pop-ups or hacked',
    'internet': 'Wi-Fi or internet',
    'hardware': 'Keyboard, ports, sound or other parts',
    'overheat': 'Overheating or loud fan',
    'data': 'Lost files or storage',
    'other': 'Not sure',
}

# Each problem: the phrases that point to it (regular expressions over the
# lower-cased description), what usually causes it, safe steps in order, and
# the service to book per device. diy=False means the steps are only about
# staying safe until a technician sees it.
PROBLEMS = [
    {'id': 'no_power', 'category': 'startup', 'devices': ALL, 'title': 'No power at all',
     'patterns': [r"no power", r"won'?t (turn|power|switch) on", r"(does ?n'?t|doesnt|not|never|cannot|can'?t) (turn|power|switch)(ing)? on",
                  r"no (lights?|led|signs? of life)", r"\bdead\b", r"walang (power|ilaw|kuryente)", r"ayaw (mag[- ]?on|bumukas|mag ?bukas|umandar)",
                  r"hindi (na )?(nag[- ]?o?on|bumubukas|nagbubukas|umaandar)", r"patay (na|ang|yung)", r"pressing the power button"],
     'cause': 'No power reaches the board: a dead battery or charger, a faulty power button, a failed power supply (desktop) or a board fault.',
     'steps': ['Plug it into a wall outlet you know works, using the original charger or power cable.',
               'Laptop or phone: leave it charging for 30 minutes, then hold the power button for 30 seconds before trying again.',
               'Desktop: check the switch on the back of the power supply is on and the cable is pushed in fully.',
               'Unplug everything else (USB drives, docks, extra monitors) and try once more.'],
     'diy': True, 'service': {'laptop': 'Laptop No-Power Troubleshooting', 'desktop': "Desktop PC Won't Turn On Diagnosis",
                              'smartphone': 'Phone or Tablet Battery Replacement', 'tablet': 'Phone or Tablet Battery Replacement'}},
    {'id': 'no_boot', 'category': 'startup', 'devices': PC, 'title': 'Turns on but does not start Windows',
     'patterns': [r"no bootable", r"boot ?device", r"operating system (not found|missing)", r"stuck (on|at) (the )?(logo|loading|boot|startup|spinning)",
                  r"boot ?loop", r"keeps? restarting", r"restarts? (over and over|repeatedly|by itself)", r"automatic repair", r"preparing automatic repair",
                  r"(won'?t|doesn'?t|not) (boot|load windows|start windows)", r"ayaw mag[- ]?boot", r"black screen with (a )?cursor", r"bios"],
     'cause': 'Windows cannot load: corrupted start-up files after an update or power cut, a failing drive, or a wrong boot setting.',
     'steps': ['Remove USB drives, memory cards and discs, then restart.',
               'Hold the power button to switch off at the Windows logo three times in a row; Windows then opens Automatic Repair.',
               'In Automatic Repair choose Advanced options, then Startup Repair.',
               'If it says no bootable device, the drive may not be detected: stop retrying and back up nothing further until it is checked.'],
     'diy': True, 'service': {'laptop': 'Operating System Boot Failure Repair', 'desktop': 'Operating System Boot Failure Repair'}},
    {'id': 'mobile_bootloop', 'category': 'startup', 'devices': MOBILE, 'title': 'Stuck on the logo or restarting',
     'patterns': [r"stuck (on|at) (the )?(logo|samsung|apple|loading|boot)", r"boot ?loop", r"keeps? restarting", r"restarts? by itself",
                  r"stuck (after|during) (an )?update", r"hindi (na )?lumalampas sa logo"],
     'cause': 'The phone or tablet software did not finish starting, often after a failed update or a full storage.',
     'steps': ['Charge it for 30 minutes first.', 'Force restart it (hold power and volume down for about 15 seconds).',
               'If it still loops, stop: a reset can erase your data, so let a technician try to save it first.'],
     'diy': True, 'service': {'smartphone': 'Phone or Tablet Software Repair', 'tablet': 'Phone or Tablet Software Repair'}},
    {'id': 'no_display', 'category': 'screen', 'devices': ALL, 'title': 'Runs but the screen stays black',
     'patterns': [r"black screen", r"no display", r"blank screen", r"screen (is |stays |goes )?(black|blank|dark)", r"fans? (spin|run|turn)s? but",
                  r"lights? (are |is )?on but", r"walang display", r"itim (lang )?(ang|yung) screen", r"no picture", r"no signal"],
     'cause': 'The device is on but no picture reaches the screen: a loose display cable, the monitor input, the graphics or RAM, or a failed screen.',
     'steps': ['Desktop: check the monitor is on, on the right input, and the cable is in the graphics card, not the board.',
               'Laptop: connect an external monitor or TV with HDMI; if that shows a picture, the laptop screen or its cable is the problem.',
               'Phone or tablet: hold power and volume down for 15 seconds to force a restart.',
               'Shine a flashlight on the screen: a very faint picture means the backlight has failed.'],
     'diy': True, 'service': {'laptop': 'Laptop Screen / LCD Replacement', 'desktop': 'Desktop Monitor Display Troubleshooting',
                              'smartphone': 'Smartphone Screen Replacement', 'tablet': 'Tablet Screen / Digitizer Replacement'}},
    {'id': 'cracked_screen', 'category': 'screen', 'devices': ALL, 'title': 'Cracked or physically damaged screen',
     'patterns': [r"crack", r"broken (screen|glass|lcd|display)", r"shatter", r"basag", r"nabagsak", r"(fell|dropped|nahulog)",
                  r"ink (spot|blot|leak)", r"black (spot|patch|blot)", r"touch (screen )?(not working|doesn'?t work|unresponsive)", r"ghost touch"],
     'cause': 'The glass or display panel is physically damaged, usually from a drop or pressure.',
     'steps': ['Back up your files or photos now while the device still works.', 'Avoid pressing on the damaged area; cover sharp glass with clear tape.'],
     'diy': False, 'service': {'laptop': 'Laptop Screen / LCD Replacement', 'desktop': 'Desktop Monitor Replacement',
                               'smartphone': 'Smartphone Screen Replacement', 'tablet': 'Tablet Screen / Digitizer Replacement'}},
    {'id': 'screen_lines', 'category': 'screen', 'devices': ALL, 'title': 'Lines, flicker or distorted picture',
     'patterns': [r"flicker", r"lines? (on|across|in) (the )?(screen|display)", r"(vertical|horizontal) lines?", r"distort", r"dim (screen|display)",
                  r"screen (is )?(dim|blinking)", r"may (guhit|linya)", r"kumukurap", r"pixel"],
     'cause': 'A loose or damaged display cable, an outdated graphics driver, or a failing screen panel.',
     'steps': ['Restart the device and check whether the lines also appear on the start-up logo (if yes, it is hardware).',
               'PC: update the graphics driver from Windows Update or the maker\'s website.',
               'Laptop: slowly open and close the lid; if the picture changes as the hinge moves, the display cable is worn.'],
     'diy': True, 'service': {'laptop': 'Laptop Screen / LCD Replacement', 'desktop': 'Desktop Monitor Display Troubleshooting',
                              'smartphone': 'Smartphone Screen Replacement', 'tablet': 'Tablet Screen / Digitizer Replacement'}},
    {'id': 'not_charging', 'category': 'battery', 'devices': ALL, 'title': 'Not charging',
     'patterns': [r"not charging", r"won'?t charge", r"doesn'?t charge", r"(charger|charging port|port) (is )?(loose|broken|not working)",
                  r"plugged in,? not charging", r"ayaw mag[- ]?charge", r"hindi (na )?nag[- ]?ch?ar?ge", r"charging (light|icon) (doesn'?t|won'?t|not)"],
     'cause': 'A worn charger or cable, lint or a loose charging port, or a battery at the end of its life.',
     'steps': ['Try a different outlet, then a different charger or cable of the same type and wattage.',
               'Look into the charging port with a light; remove lint gently with a wooden toothpick (never metal).',
               'Restart the device while it is plugged in.'],
     'diy': True, 'service': {'laptop': 'Laptop Charging Port Repair', 'desktop': 'Desktop PC Power Supply Replacement',
                              'smartphone': 'Phone or Tablet Charging Port Repair', 'tablet': 'Phone or Tablet Charging Port Repair'}},
    {'id': 'battery_drain', 'category': 'battery', 'devices': ALL - {'desktop'}, 'title': 'Battery drains fast or dies suddenly',
     'patterns': [r"(battery|batt) (drain|dies|empties|goes down|drops)", r"drains? (fast|quickly)", r"(dies|shuts? (off|down)) (at|around) \d+ ?%",
                  r"battery (health|life) (is )?(low|bad|poor)", r"mabilis (ma[- ]?lowbat|malowbat|maubos)", r"lowbat"],
     'cause': 'The battery has worn out (normal after 2 to 3 years) or an app keeps the device busy in the background.',
     'steps': ['Check battery health: Windows run "powercfg /batteryreport"; iPhone Settings > Battery; Android Settings > Battery.',
               'Close apps you are not using and lower screen brightness.',
               'If health is below about 80% or it shuts off above 20%, the battery needs replacing.'],
     'diy': True, 'service': {'laptop': 'Laptop Battery Replacement', 'smartphone': 'Phone or Tablet Battery Replacement',
                              'tablet': 'Phone or Tablet Battery Replacement'}},
    {'id': 'swollen_battery', 'category': 'battery', 'devices': ALL - {'desktop'}, 'title': 'Swollen battery',
     'patterns': [r"swollen", r"swell", r"bulg", r"puff", r"lumobo", r"namamaga", r"(screen|case|back|trackpad|touchpad) (is )?(lifting|popping|pushed)"],
     'cause': 'The battery is swelling. This is a fire risk and the battery must be replaced.',
     'steps': ['Stop using and stop charging the device now.', 'Keep it away from heat and do not press on it or try to remove the battery yourself.'],
     'diy': False, 'urgent': True,
     'service': {'laptop': 'Laptop Battery Replacement', 'smartphone': 'Phone or Tablet Battery Replacement',
                 'tablet': 'Phone or Tablet Battery Replacement'}},
    {'id': 'slow', 'category': 'slow', 'devices': ALL, 'title': 'Slow or lagging',
     'patterns': [r"\bslow\b", r"lag", r"takes? (forever|long|ages|minutes)", r"(disk|cpu|memory) (usage )?(at )?100", r"bagal", r"mabagal",
                  r"nag[- ]?ha?hang", r"hang(ing|s)?\b", r"not responding"],
     'cause': 'Too many programs starting with the device, a nearly full drive, an old hard disk, too little memory, or hidden malware.',
     'steps': ['Restart the device (a full restart, not sleep).', 'Free up space so at least 15% of the drive is empty.',
               'PC: open Task Manager > Startup and disable programs you do not need at start-up.',
               'PC: if Task Manager shows Disk at 100% for long periods, an SSD upgrade will help most.'],
     'diy': True, 'service': {'laptop': 'Slow Computer Optimization', 'desktop': 'Slow Computer Optimization',
                              'smartphone': 'Phone or Tablet Software Repair', 'tablet': 'Phone or Tablet Software Repair'}},
    {'id': 'freeze', 'category': 'slow', 'devices': PC, 'title': 'Freezes or restarts on its own',
     'patterns': [r"freez", r"random(ly)? (restart|shut ?down|turns? off)", r"shuts? (down|off) (by itself|on its own|randomly)",
                  r"nag[- ]?f?reeze", r"biglang (namamatay|nag[- ]?restart|nag[- ]?shut ?down)"],
     'cause': 'Overheating, failing memory or drive, or a faulty driver.',
     'steps': ['Note what you were doing when it froze (gaming, charging, a certain app).', 'Clean the air vents and use it on a hard, flat surface.',
               'Install all Windows and driver updates.'],
     'diy': True, 'service': {'laptop': 'System Freeze and Random Restart Troubleshooting',
                              'desktop': 'System Freeze and Random Restart Troubleshooting'}},
    {'id': 'bsod', 'category': 'software', 'devices': PC, 'title': 'Blue screen error',
     'patterns': [r"blue screen", r"bsod", r"stop code", r"your pc ran into a problem", r"critical process died", r"irql", r"kernel"],
     'cause': 'A driver, recent update or failing hardware (often memory or the drive) is crashing Windows.',
     'steps': ['Write down or photograph the stop code shown on the blue screen.', 'Undo anything added just before it started (new program, driver or device).',
               'Install all Windows updates, then run "sfc /scannow" in an administrator Command Prompt.'],
     'diy': True, 'service': {'laptop': 'Blue Screen Error Troubleshooting', 'desktop': 'Blue Screen Error Troubleshooting'}},
    {'id': 'app_crash', 'category': 'software', 'devices': ALL, 'title': 'An app or program keeps crashing',
     'patterns': [r"(app|program|software|game|application) (keeps? )?(crash|clos|stop|not opening|won'?t open)", r"keeps? (crashing|closing)",
                  r"has stopped", r"error (message|code)", r"won'?t (open|install)", r"ayaw (mag[- ]?open|bumukas ang app)", r"nagka[- ]?crash"],
     'cause': 'A corrupted installation, a missing update, or an app that doesn\'t suit your system version.',
     'steps': ['Restart the device, then update the app and the system.', 'Uninstall and reinstall the app.',
               'Note the exact error message; it tells the technician most of the story.'],
     'diy': True, 'service': {'laptop': 'Application Installation and Error Fixes', 'desktop': 'Application Installation and Error Fixes',
                              'smartphone': 'Phone or Tablet Software Repair', 'tablet': 'Phone or Tablet Software Repair'}},
    {'id': 'update_fail', 'category': 'software', 'devices': PC, 'title': 'Windows update fails',
     'patterns': [r"update (fail|stuck|error|won'?t install)", r"windows update", r"undoing changes", r"couldn'?t complete the updates"],
     'cause': 'Corrupted update files, too little free space, or an incompatible driver.',
     'steps': ['Free up at least 20 GB of space.', 'Run Settings > System > Troubleshoot > Windows Update.', 'Restart and try the update again.'],
     'diy': True, 'service': {'laptop': 'Windows Update Troubleshooting', 'desktop': 'Windows Update Troubleshooting'}},
    {'id': 'malware', 'category': 'virus', 'devices': ALL, 'title': 'Malware or unwanted pop-ups',
     'patterns': [r"virus", r"malware", r"pop[- ]?ups?", r"(ads?|advertisements?) (everywhere|keep|pop)", r"redirect", r"hack",
                  r"ransom", r"(files?|documents?) (are )?encrypted", r"strange (programs?|apps?|toolbar)", r"may virus"],
     'cause': 'Unwanted software was installed, often with a free download, a cracked program or a fake update.',
     'steps': ['Disconnect from the internet if files are being renamed or locked.', 'Run a full scan with Windows Security (or your antivirus).',
               'Uninstall programs or apps you don\'t recognise, and change your important passwords from another, clean device.'],
     'diy': True, 'service': {'laptop': 'Virus and Malware Removal', 'desktop': 'Virus and Malware Removal',
                              'smartphone': 'Virus and Malware Removal', 'tablet': 'Virus and Malware Removal'}},
    {'id': 'wifi', 'category': 'internet', 'devices': ALL, 'title': 'Wi-Fi not connecting',
     'patterns': [r"wi-?fi", r"wireless", r"no internet", r"can'?t connect", r"not connecting", r"(internet|connection) (is )?(slow|drops|keeps dropping|unstable)",
                  r"limited (access|connectivity)", r"walang (internet|wifi|signal)", r"ayaw (mag[- ]?connect|kumonek)", r"network adapter"],
     'cause': 'Router trouble, a disabled or outdated network adapter driver, or a faulty Wi-Fi card.',
     'steps': ['Check whether other devices can use the same Wi-Fi; if not, restart the router.',
               'Turn airplane mode on and off, then forget the network and connect again.',
               'PC: run Settings > Network > Network troubleshooter and update the Wi-Fi driver.'],
     'diy': True, 'service': {'laptop': 'Driver Installation and Repair', 'desktop': 'Wi-Fi Adapter Installation',
                              'smartphone': 'Phone or Tablet Software Repair', 'tablet': 'Phone or Tablet Software Repair'}},
    {'id': 'keyboard', 'category': 'hardware', 'devices': PC, 'title': 'Keyboard or touchpad problem',
     'patterns': [r"keyboard", r"keys? (not working|stuck|don'?t work|missing|typing wrong)", r"touch ?pad", r"track ?pad",
                  r"mouse (not working|doesn'?t move|stuck)", r"(spill|spilled|natapunan) (on|ang|yung)? ?(the )?keyboard"],
     'cause': 'Dirt or liquid under the keys, a driver problem, or a worn keyboard or touchpad.',
     'steps': ['Restart and check whether the keys work in the BIOS or on the login screen (if not, it is hardware).',
               'Connect a USB keyboard or mouse to confirm.', 'If liquid was spilled, switch it off, unplug it and keep it off.'],
     'diy': True, 'service': {'laptop': 'Laptop Keyboard Repair', 'desktop': 'Computer Keyboard Replacement'}},
    {'id': 'ports_sound', 'category': 'hardware', 'devices': ALL, 'title': 'Ports, speakers, microphone or camera',
     'patterns': [r"usb (port )?(not working|doesn'?t work|dead|loose)", r"no sound", r"speaker", r"microphone|\bmic\b",
                  r"camera (not working|black|blurry)", r"walang (tunog|sound)", r"headphone", r"hdmi (port )?(not working|loose)"],
     'cause': 'A worn or dirty port, a muted or misconfigured output, a driver, or a failed part.',
     'steps': ['Check the volume, the selected output device and that the app has permission to use the mic or camera.',
               'Try another port or another cable or accessory.', 'Restart and update drivers or the system.'],
     'diy': True, 'service': {'laptop': 'Laptop Speaker Replacement', 'desktop': 'Driver Installation and Repair',
                              'smartphone': 'Speaker and Microphone Repair', 'tablet': 'Speaker and Microphone Repair'}},
    {'id': 'water', 'category': 'hardware', 'devices': ALL, 'title': 'Liquid damage',
     'patterns': [r"water", r"liquid", r"spill", r"wet", r"(coffee|juice|soda|rain)", r"nabasa", r"nalaglag sa (tubig|cr|banyo)", r"natapunan", r"lubog"],
     'cause': 'Liquid inside can short the board and causes corrosion that worsens by the hour.',
     'steps': ['Switch it off now and unplug it; do not try to turn it on to "test" it.', 'Remove the case and SIM / memory card if you can.',
               'Do not use rice or a hair dryer; bring it in as soon as possible.'],
     'diy': False, 'urgent': True,
     'service': {'laptop': 'Water Damage Cleaning and Assessment', 'desktop': 'Motherboard Troubleshooting',
                 'smartphone': 'Water Damage Cleaning and Assessment', 'tablet': 'Water Damage Cleaning and Assessment'}},
    {'id': 'overheat', 'category': 'overheat', 'devices': ALL, 'title': 'Overheating or loud fan',
     'patterns': [r"overheat", r"(too |very |so )?hot", r"(fan|fans) (is |are )?(loud|noisy|always on|spinning fast|grinding)", r"loud fan",
                  r"mainit", r"umiinit", r"burning smell", r"smell(s)? (like )?burn"],
     'cause': 'Dust blocking the fan and vents, dried thermal paste, or a failing fan.',
     'steps': ['Use it on a hard, flat surface, never on a bed or pillow.', 'Close heavy programs and games and see if it cools down.',
               'If you smell burning, switch it off and unplug it right away.'],
     'diy': True, 'service': {'laptop': 'Overheating and Thermal Paste Replacement', 'desktop': 'CPU Cooling Fan Replacement',
                              'smartphone': 'Phone or Tablet Battery Replacement', 'tablet': 'Phone or Tablet Battery Replacement'}},
    {'id': 'drive_failing', 'category': 'data', 'devices': PC, 'title': 'Drive failing or not detected',
     'patterns': [r"click(ing)? (noise|sound)", r"(drive|disk|hdd|ssd) (not detected|not showing|failing|failed|making noise|corrupt)",
                  r"smart (error|failure)", r"(format|repair) (the )?(disk|drive) (prompt|before)", r"hindi (na )?ma[- ]?detect"],
     'cause': 'The hard drive or SSD is failing. Every restart risks more data loss.',
     'steps': ['Stop using the computer and do not let any tool "repair" or format the drive.', 'If it still starts, copy your most important files first.'],
     'diy': False, 'urgent': True,
     'service': {'laptop': 'HDD File Recovery', 'desktop': 'HDD File Recovery'}},
    {'id': 'lost_files', 'category': 'data', 'devices': ALL, 'title': 'Deleted or missing files',
     'patterns': [r"deleted", r"(lost|missing) (my )?(files?|photos?|documents?|data|pictures?)", r"accidentally (deleted|formatted)",
                  r"nabura", r"nawala (ang|yung) (files?|pictures?|photos?)", r"formatted"],
     'cause': 'Files were deleted, overwritten, or the folder was moved.',
     'steps': ['Stop saving new files on that device or drive; new data overwrites what can be recovered.',
               'Check the Recycle Bin, Recently Deleted (phones) and any cloud backup.'],
     'diy': True, 'service': {'laptop': 'Deleted File Recovery', 'desktop': 'Deleted File Recovery',
                              'smartphone': 'Data Backup and Restoration', 'tablet': 'Data Backup and Restoration'}},
]

# Where to go when nothing specific matched (low confidence): a diagnosis service per device.
DIAGNOSIS_SERVICE = {'laptop': 'RAM Detection and Hardware Fault Diagnosis', 'desktop': 'RAM Detection and Hardware Fault Diagnosis',
                     'smartphone': 'Phone or Tablet Software Repair', 'tablet': 'Phone or Tablet Software Repair'}

UNSURE = [r"(i )?(don'?t|dont|do not) know", r"not sure", r"\bidk\b", r"no idea", r"(hindi|di) ko (po )?alam", r"\bewan\b",
          r"\bunknown\b", r"no clue", r"hindi ko sure", r"not certain"]

# Plain words people use when describing a device problem (English and Filipino).
# A description must contain real words, not random letters.
_COMMON = """
a about after again all also always am an and any are as at away back bad be because been before being bigla biglang
both broke broken but by can cannot cant charge charger charging check computer could daily day days did didnt do does doesnt
dont down drop dropped during each even ever every fast few files first fix for from fully game games get gets go goes going
got had has have having he her his home hours how i if im in inside into is isnt it its just keep keeps last later laptop
like little load loading long lot make many may me minute minutes mode more morning most much my need needs never new next
night no not now of off often old on once one only open or other our out over phone please power pressed press problem
problems properly really right same say screen see seems shows since slow so some something sometimes start started
starts still stop stopped suddenly than that the their them then there these they thing things this those through time
times to today too try tried trying turn turned turns under until up update updated use used using very was wasnt
way we week weeks well went were what when where which while why will with without work worked working works would
yesterday yet you your device desktop pc tablet ipad iphone samsung android windows mac macbook monitor display mouse
keyboard battery port usb cable wifi internet sound app apps error message light lights noise hot fan file photo photos
po ang ng sa na ko ako ito yung iyong mga pag nag hindi ayaw di wala walang lang kasi pero tapos kapag kung nung noong
din rin naman sya siya niya nya ba pa ay at may meron talaga sobra medyo ulit minsan palagi lagi bago luma gamit
cellphone selpon cp charger kanina kahapon ngayon gabi umaga araw linggo
"""


def _vocabulary():
    words = set(_COMMON.split())
    for p in PROBLEMS:
        for pattern in p['patterns']:
            words.update(w for w in re.findall(r'[a-z]{2,}', pattern))
        words.update(re.findall(r'[a-z]{2,}', (p['title'] + ' ' + p['cause']).lower()))
    for label in CATEGORIES.values():
        words.update(re.findall(r'[a-z]{2,}', label.lower()))
    return words


VOCAB = _vocabulary()
_KEY_ROWS = ('qwertyuiop', 'asdfghjkl', 'zxcvbnm')


def _gibberish(token):
    """A token that looks like keyboard mashing rather than a word."""
    t = token.lower()
    if len(t) < 4 or t in VOCAB:
        return False
    vowels = sum(ch in 'aeiouy' for ch in t)
    if vowels == 0 or vowels / len(t) < 0.2:
        return True
    if re.search(r'[^aeiouy\W\d]{5,}', t) or re.search(r'(.)\1{3,}', t):
        return True
    return any(t in row or t in row[::-1] for row in _KEY_ROWS)


def is_specific(text):
    """(True, '') if text is a real, specific description of a problem; otherwise
    (False, what to fix). Shared by the troubleshooter and the booking form."""
    text = (text or '').strip()
    tokens = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text)
    if len(text) < 15 or len(tokens) < 3:
        return False, 'Please be specific: describe what the device does in a full sentence (for example, "My laptop shows a black screen after I dropped it").'
    junk = [t for t in tokens if _gibberish(t)]
    known = [t for t in tokens if t.lower().replace("'", '') in VOCAB or t.lower() in VOCAB]
    if len(junk) * 3 >= len(tokens) or len(known) < 2:
        return False, 'Please be specific: your description looks like random letters. Tell us what happens, when it started and anything you see or hear.'
    return True, ''


def _hits(problem, text):
    found = []
    for pattern in problem['patterns']:
        m = re.search(pattern, text)
        if m:
            found.append(m.group(0).strip())
    return found


def diagnose(device, category, description):
    """Match a description to the knowledge base. Returns a dict with
    status ('ok' or 'unclear'), confidence, the problem, steps and service name."""
    device = device if device in DEVICES else 'laptop'
    category = category if category in CATEGORIES else 'other'
    ok, why = is_specific(description)
    if not ok:
        return {'status': 'unclear', 'message': why}
    text = ' '.join(description.lower().split())
    unsure = any(re.search(p, text) for p in UNSURE)

    scored = []
    for p in PROBLEMS:
        if device not in p['devices']:
            continue
        hits = _hits(p, text)
        if hits:
            # Safety problems (liquid, swollen battery, failing drive) win a tie.
            scored.append((len(hits) * 2 + (1 if p['category'] == category else 0) + (1 if p.get('urgent') else 0),
                           p, hits))
    scored.sort(key=lambda s: -s[0])

    if not scored:
        return {'status': 'ok', 'confidence': 'low', 'problem': None, 'evidence': [], 'steps': [],
                'title': 'We could not match this to a known problem',
                'cause': 'Your description does not point to one specific fault, so guessing could send you the wrong way.',
                'reason': 'You said you are not sure of the cause, and no specific symptom was mentioned.' if unsure
                else 'No specific symptom we recognise was mentioned.',
                'advice': 'Book a diagnosis so a technician can test the device, or message our support team first.',
                'service': DIAGNOSIS_SERVICE[device], 'urgent': False, 'diy': False}

    _, best, hits = scored[0]
    agrees = category in ('other', best['category'])
    if unsure:
        confidence = 'low'
        reason = 'You said you don\'t know the cause, so this is only a possibility.'
    elif best.get('urgent'):
        confidence = 'high'
        reason = 'You described a problem that needs a technician straight away.'
    elif len(hits) >= 2 and agrees:
        confidence = 'high'
        reason = 'Several of the symptoms you described match this problem.'
    elif len(hits) >= 2 or (agrees and category != 'other'):
        confidence = 'medium' if not agrees else 'high'
        reason = ('Your symptoms match this problem, though you chose a different problem type.' if not agrees
                  else 'Your description matches the problem type you chose.')
    else:
        confidence = 'medium'
        reason = 'Only one symptom matched; more detail would make this more certain.'

    if confidence == 'low':
        advice = 'Book a repair or message our support team so a technician can confirm the cause before anything is changed.'
    elif not best['diy'] or best.get('urgent'):
        advice = 'Do only the safety steps below, then book a repair as soon as possible.'
    elif confidence == 'high':
        advice = 'Try these steps in order. If the problem continues, book a repair.'
    else:
        advice = 'You can try the safe steps below. If you are unsure at any point, book a repair or message support.'

    return {'status': 'ok', 'confidence': confidence, 'problem': best['id'], 'title': best['title'],
            'cause': best['cause'], 'steps': best['steps'] if confidence != 'low' or not best['diy'] else [],
            'evidence': hits[:4], 'reason': reason, 'advice': advice, 'urgent': bool(best.get('urgent')),
            'diy': best['diy'], 'service': best['service'].get(device) or DIAGNOSIS_SERVICE[device],
            'category_mismatch': None if agrees else CATEGORIES.get(best['category'])}
