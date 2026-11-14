"""DEVTech's FAQ chatbot: answers the common questions customers ask, in English
or Tagalog/Taglish, from a fixed list of answers about how DEVTech works. It only
answers these FAQs; anything else goes to the team chat. No AI service is called;
nothing leaves the server.

answer(question, shop) -> {'id', 'answer', 'links', 'suggestions', 'confident'}
`shop` carries the live details used in answers (booking fee, hours, phone...).
When nothing matches well, it says so and offers a person instead of guessing.
"""
import re

# Each FAQ: words that point to it (stems are fine: 'cancel' matches 'cancelled'),
# phrases that settle it, the answer (str.format fields from `shop`), and links
# as (label, endpoint name).
FAQS = [
    {'id': 'book', 'q': 'How do I book a repair?',
     'words': ['book', 'booking', 'schedule', 'appointment', 'repair', 'pa-repair', 'paayos', 'magpaayos', 'reserve', 'slot'],
     'phrases': ['how to book', 'how do i book', 'paano mag book', 'paano magpa', 'make a booking', 'book a repair'],
     'answer': 'Open Service Request, pick your device and the service, describe the problem, choose a date and an '
               'hourly slot (8 AM to 5 PM), then confirm. You pay the {fee_text} by QR to confirm the slot. '
               'Not sure which service you need? Try the Troubleshooting assistant first.',
     'links': [('Book a repair', 'book_appointment'), ('Troubleshooting assistant', 'user_troubleshooting')]},
    {'id': 'fee', 'q': 'What is the booking fee?',
     'words': ['fee', 'deposit', 'downpayment', 'down', 'reservation', 'deduct', 'deducted', 'bawas', 'refundable'],
     'phrases': ['booking fee', 'why do i pay', 'reservation fee', 'down payment'],
     'answer': '{fee_answer}',
     'links': [('My transactions', 'user_transactions')]},
    {'id': 'pay', 'q': 'How can I pay?',
     'words': ['pay', 'payment', 'gcash', 'maya', 'card', 'cash', 'bayad', 'magbayad', 'qr', 'qrph', 'bank', 'cod', 'method'],
     'phrases': ['how can i pay', 'how to pay', 'paano magbayad', 'payment method', 'pay by qr', 'cash after repair'],
     'answer': 'Repairs: pay by QR Ph (scan with GCash, Maya or your bank app, confirmed automatically) or by card. '
               'You can also choose C.A.R, Cash After Repair, and pay the balance at the shop when your device is '
               'ready. Shop orders can be paid by QR or cash on delivery.',
     'links': [('My transactions', 'user_transactions')]},
    {'id': 'qr', 'q': 'How do I pay with the QR code?',
     'words': ['scan', 'qr', 'code', 'expired', 'expire', 'new', 'generate'],
     'phrases': ['scan the qr', 'qr code', 'qr expired', 'new code', 'how to scan'],
     'answer': 'Press "Pay by QR" on the payment, then scan the code with GCash, Maya or your bank app and pay the '
               'exact amount. The page confirms it by itself within a few seconds. A code expires after a while; '
               'press "Get a new code" if it does. You can also pay by card from the same window.',
     'links': [('My transactions', 'user_transactions')]},
    {'id': 'paid_pending', 'q': 'I paid but it still says pending',
     'words': ['pending', 'paid', 'nabayaran', 'nagbayad', 'deducted', 'charged', 'unconfirmed', 'stuck'],
     'phrases': ['already paid', 'still pending', 'nagbayad na', 'paid but', 'not confirmed', 'money was deducted'],
     'answer': 'QR payments usually confirm within a minute. Open My Transactions and refresh the page. If it still '
               'shows pending after 15 minutes, message our team with the transaction number and a screenshot of '
               'your receipt, and we will check it with PayMongo. Please do not pay twice.',
     'links': [('My transactions', 'user_transactions')], 'human': True},
    {'id': 'cancel', 'q': 'Can I cancel a booking or order?',
     'words': ['cancel', 'cancellation', 'icancel', 'kansel', 'stop', 'withdraw', 'ayaw'],
     'phrases': ['cancel my booking', 'cancel my order', 'cancel booking', 'cancel order', 'i want to cancel'],
     'answer': 'Yes. Open My Bookings or My Orders and cancel it while the work or delivery has not started. Anything '
               'you already paid online is refunded in full to the card or e-wallet you used.',
     'links': [('My bookings', 'total_bookings'), ('My orders', 'user_orders')]},
    {'id': 'refund', 'q': 'How do refunds work?',
     'words': ['refund', 'refunded', 'ibalik', 'money', 'back', 'return'],
     'phrases': ['get my money back', 'refund status', 'when will i get', 'ibalik ang pera', 'my refund'],
     'answer': 'Refunds go back to the card or e-wallet you paid with. You can follow each refund under My '
               'Transactions. How fast it shows in your account depends on your bank or e-wallet.',
     'links': [('My transactions', 'user_transactions')]},
    {'id': 'track', 'q': 'How do I track my repair?',
     'words': ['track', 'status', 'progress', 'update', 'monitor', 'nasaan', 'ready', 'done', 'tapos', 'kailan'],
     'phrases': ['track my repair', 'status of my repair', 'is my laptop ready', 'is it ready', 'tapos na ba', 'where is my'],
     'answer': 'Monitor Device shows your repair live, stage by stage: requested, assigned, diagnosis, on repair, '
               'ready for collection, released, with notes from your technician. You also get a notification at '
               'each step.',
     'links': [('Monitor device', 'monitor_device')]},
    {'id': 'approval', 'q': 'The technician asked for my approval',
     'words': ['approval', 'approve', 'approved', 'extra', 'additional', 'dagdag', 'hold', 'decline'],
     'phrases': ['extra cost', 'additional cost', 'on hold', 'approval needed', 'dagdag bayad'],
     'answer': 'If the technician finds more work than you booked, the job pauses and Monitor Device shows what they '
               'found, the extra cost and time. Approve or decline there; nothing extra is done or charged without '
               'your OK.',
     'links': [('Monitor device', 'monitor_device')]},
    {'id': 'price', 'q': 'How much does a repair cost?',
     'words': ['price', 'cost', 'how', 'much', 'magkano', 'presyo', 'rate', 'quotation', 'quote', 'estimate', 'parts'],
     'phrases': ['how much', 'magkano', 'price list', 'starting price', 'cost of'],
     'answer': 'Every service shows its starting price in the service list. Replacement parts depend on your model '
               'and are quoted before work starts. If the job turns out bigger, we ask you first.',
     'links': [('Services and prices', 'service_catalog')]},
    {'id': 'time', 'q': 'How long does a repair take?',
     'words': ['long', 'days', 'hours', 'gaano', 'katagal', 'duration', 'turnaround', 'quick', 'fast', 'same'],
     'phrases': ['how long', 'gaano katagal', 'same day', 'how many days'],
     'answer': 'Most services take one to a few hours of work; each service lists its usual time. Jobs that need a '
               'part ordered take longer, and the technician tells you the extra days before you approve.',
     'links': [('Services and prices', 'service_catalog')]},
    {'id': 'home', 'q': 'Do you offer home service?',
     'words': ['home', 'house', 'bahay', 'onsite', 'on-site', 'visit', 'pickup', 'location', 'pin'],
     'phrases': ['home service', 'go to my house', 'sa bahay', 'on site', 'pick up my'],
     'answer': 'Yes, inside Tacloban City. When booking, choose home service and pin your location on the map. '
               'Otherwise bring the device to the shop for in-shop repair.',
     'links': [('Book a repair', 'book_appointment')]},
    {'id': 'shop', 'q': 'Where is the shop and when are you open?',
     'words': ['where', 'address', 'located', 'location', 'shop', 'store', 'branch', 'open', 'hours', 'saan', 'oras', 'contact',
               'phone', 'number', 'call', 'email'],
     'phrases': ['where are you', 'where is', 'saan kayo', 'what time', 'open today', 'contact number', 'phone number',
                 'business hours', 'store hours'],
     'answer': '{shop_answer}',
     'links': []},
    {'id': 'delivery', 'q': 'How does delivery work for shop orders?',
     'words': ['delivery', 'deliver', 'rider', 'shipping', 'ship', 'order', 'parcel', 'dating', 'arrive'],
     'phrases': ['when will my order', 'delivery fee', 'same day delivery', 'kailan darating'],
     'answer': 'Shop orders are delivered by our riders. My Orders shows the estimated arrival and the rider once it '
               'is on the way. Orders placed before 4 PM can arrive the same day when you are nearby.',
     'links': [('My orders', 'user_orders'), ('Shop', 'user_shop')]},
    {'id': 'data', 'q': 'Will my files be safe?',
     'words': ['data', 'files', 'photos', 'backup', 'privacy', 'safe', 'recover', 'recovery', 'deleted', 'lost'],
     'phrases': ['my files', 'back up', 'recover my', 'data recovery', 'lost files'],
     'answer': 'We back up your files before reinstalling or replacing a drive whenever the drive can still be read. '
               'Data recovery is not guaranteed: physically damaged drives may need a specialist lab, and we tell '
               'you what is possible after diagnosis.',
     'links': [('Data recovery services', 'service_catalog')]},
    {'id': 'devices', 'q': 'Which devices do you repair?',
     'words': ['devices', 'device', 'repair', 'phone', 'cellphone', 'smartphone', 'tablet', 'ipad', 'monitor', 'printer',
               'desktop', 'laptop', 'hdd', 'ssd'],
     'phrases': ['do you repair', 'do you fix', 'can you fix', 'nag-aayos ba kayo', 'what devices'],
     'answer': 'Laptops, desktop PCs, tablets, smartphones, monitors and storage devices such as hard drives, SSDs and '
               'flash drives. We no longer service printers or all-in-one PCs.',
     'links': [('Services and prices', 'service_catalog')]},
    {'id': 'diagnose', 'q': "I don't know what's wrong with my device",
     'words': ['wrong', 'problem', 'broken', 'sira', 'issue', 'unknown', 'diagnose', 'diagnosis', 'troubleshoot'],
     'phrases': ["don't know", 'not sure what', 'hindi ko alam', 'what is wrong', 'ayaw gumana'],
     'answer': 'Try the Troubleshooting assistant: pick your device, describe what happens, and it suggests safe '
               'checks and the right service. If it is still unclear, book a diagnosis and a technician will find '
               'the fault.',
     'links': [('Troubleshooting assistant', 'user_troubleshooting')]},
    {'id': 'account', 'q': 'How do I change my profile or password?',
     'words': ['password', 'account', 'profile', 'photo', 'picture', 'email', 'name', 'login', 'forgot', 'reset'],
     'phrases': ['change my password', 'forgot password', 'profile picture', 'change my name', 'update my email'],
     'answer': 'Open Profile to change your name, phone, photo and password. If you forgot your password, use '
               '"Forgot Password?" on the login page and follow the link we email you.',
     'links': [('Profile', 'user_profile')]},
    {'id': 'human', 'q': 'Talk to a person',
     'words': ['human', 'person', 'agent', 'staff', 'admin', 'someone', 'tao', 'representative', 'team'],
     'phrases': ['talk to a person', 'talk to someone', 'real person', 'customer service', 'kausapin'],
     'answer': 'Sure. Press "Message our team" and write in the chat beside this box; a person from the shop replies there.',
     'links': [], 'human': True},
]

SUGGESTIONS = ['How do I book a repair?', 'What is the booking fee?', 'How can I pay?', 'How do I track my repair?']
STOP = {'a', 'an', 'the', 'i', 'my', 'me', 'to', 'is', 'it', 'do', 'does', 'can', 'of', 'for', 'and', 'or', 'in',
        'on', 'at', 'you', 'your', 'we', 'po', 'ko', 'ang', 'ng', 'sa', 'na', 'ba', 'mo', 'yung', 'lang', 'please', 'pls'}
GREETINGS = {'hi', 'hello', 'hey', 'good', 'morning', 'afternoon', 'evening', 'kumusta', 'musta', 'helo'}
THANKS = {'thanks', 'thank', 'salamat', 'ty', 'okay', 'ok', 'noted'}


def _words(text):
    return [w for w in re.findall(r"[a-z0-9'-]+", text.lower()) if w not in STOP]


# The word that says it all for a question: one of these is enough to answer
# ("paano mag cancel ng booking" is about cancelling, not booking).
KEY_WORDS = {
    'book': ['book', 'appointment', 'schedule', 'magpaayos', 'paayos'],
    'fee': ['fee', 'deposit', 'downpayment', 'reservation'],
    'pay': ['pay', 'payment', 'gcash', 'maya', 'bayad', 'magbayad', 'card', 'cod'],
    'qr': ['qr', 'scan', 'expired'],
    'paid_pending': ['pending', 'nabayaran', 'nagbayad'],
    'cancel': ['cancel', 'cancellation', 'icancel', 'kansel'],
    'refund': ['refund', 'refunded', 'ibalik'],
    'track': ['track', 'tracking', 'monitor', 'status', 'progress'],
    'approval': ['approval', 'approve', 'dagdag'],
    'price': ['price', 'magkano', 'presyo', 'cost', 'quotation'],
    'time': ['katagal', 'duration', 'turnaround'],
    'home': ['home', 'bahay', 'onsite'],
    'shop': ['address', 'located', 'location', 'hours', 'saan', 'contact'],
    'delivery': ['delivery', 'deliver', 'rider', 'shipping', 'darating'],
    'data': ['backup', 'data', 'files', 'privacy'],
    'devices': ['printer', 'ipad', 'devices'],
    'account': ['password', 'profile', 'account'],
    'human': ['human', 'person', 'agent', 'tao', 'representative'],
}


def _match(w, k):
    return w == k or (len(k) >= 4 and w.startswith(k)) or (len(w) >= 4 and k.startswith(w))


def _score(faq, text, words):
    score = sum(3 for p in faq['phrases'] if p in text)
    keys = KEY_WORDS.get(faq['id'], [])
    for w in words:
        if any(w == k or (len(k) >= 5 and w.startswith(k)) for k in keys):   # 'booking' is not the key 'book'
            score += 2
        elif any(_match(w, k) for k in faq['words']):
            score += 1
    return score


def _fill(template, shop):
    return template.format(**shop)


def shop_details(site, booking_fee):
    """The live values answers use: the booking fee and the shop's details."""
    fee = int(booking_fee or 0)
    contact = [f'Call or text {site.get("phone")}.' if site.get('phone') else '',
               f'Email {site.get("email")}.' if site.get('email') else '']
    return {
        'fee_text': f'PHP {fee} booking fee' if fee else 'booking',
        'fee_answer': (f'The booking fee is PHP {fee}. You pay it by QR when you book to confirm your slot, and it is '
                       f'deducted from your final bill, so it is not an extra charge. If the booking is cancelled, a '
                       f'paid fee is refunded to the card or e-wallet you used.') if fee else
                      'There is no booking fee at the moment; you pay the service after it is confirmed.',
        'shop_answer': ' '.join(x for x in [
            f'We are at {site.get("address") or "Tacloban City, Leyte"}.',
            f'Open {site.get("hours")}.' if site.get('hours') else '',
            *contact] if x),
    }


def answer(question, shop):
    text = ' '.join((question or '').lower().split())[:500]
    words = _words(text)
    if not words or not re.search(r'[a-z]{2}', text):
        return {'id': None, 'answer': 'Please type your question in a few words, for example "How can I pay?".',
                'links': [], 'suggestions': SUGGESTIONS, 'confident': False}
    if set(words) <= GREETINGS | {'po'}:
        return {'id': 'hello', 'answer': 'Hi! I answer common questions about bookings, payments, orders and repairs. '
                                         'What would you like to know?',
                'links': [], 'suggestions': SUGGESTIONS, 'confident': True}
    if set(words) <= THANKS | GREETINGS:
        return {'id': 'thanks', 'answer': "You're welcome! Ask me anything else, or message our team in the chat.",
                'links': [], 'suggestions': [], 'confident': True}

    ranked = sorted(((_score(f, text, words), i, f) for i, f in enumerate(FAQS)), key=lambda t: (-t[0], t[1]))
    best_score, _, best = ranked[0]
    if best_score < 2:
        return {'id': None,
                'answer': "I only know the common questions, so I can't answer that one. Our team can: press "
                          '"Message our team" and write to us in the chat. Or pick one of these questions.',
                'links': [], 'suggestions': SUGGESTIONS, 'confident': False, 'human': True}
    related = [f['q'] for s, _, f in ranked[1:4] if s >= 2]
    return {'id': best['id'], 'answer': _fill(best['answer'], shop), 'links': best['links'],
            'suggestions': related or [q for q in SUGGESTIONS if q != best['q']][:3],
            'confident': True, 'human': bool(best.get('human'))}
