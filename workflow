
Bot Automation Logic
TLS Visa Appointment Bot Flow (Human-like Automation)
Step 1: Start – Choose Country Page
Pending
https://visas-fr.tlscontact.com/visa/ma
•Bot opens the main TLS Morocco visa page
•Waits for city selection
Step 2: Redirect to City Home Page
Pending
Fes: https://fr.tlscontact.com/visa/ma/maFEZ2fr/home
Tanger: https://fr.tlscontact.com/visa/ma/maTNG2fr/home
Oujda: https://fr.tlscontact.com/visa/ma/maOUD2fr/home
Casablanca: https://fr.tlscontact.com/visa/ma/maCAS2fr/home
Agadir: https://fr.tlscontact.com/visa/ma/maAGA2fr/home
Marrakech: https://fr.tlscontact.com/visa/ma/maRAK2fr/home
Rabat: https://fr.tlscontact.com/visa/ma/maRBA2fr/home
•Bot opens selected city homepage
•Bypasses Cloudflare verification
Step 3: Authentication via OAuth
Pending
https://i2-auth.visas-fr.tlscontact.com/auth/realms/atlas/protocol/openid-connect/auth?...
•Bot fills login credentials
•Submits login
•Waits for redirection
Step 4: Book Detail Page
Pending
https://fr.tlscontact.com/formGroup/ma/maAGA2fr
•Bot fills required booking information
•Continues to next step
Step 5: Personal Info Page
Pending
https://fr.tlscontact.com/personal/ma/maAGA2fr/19349555
•Bot locates and clicks the "Book Appointment" button
Step 6: Calendar Page
Pending
https://fr.tlscontact.com/appointment/ma/maAGA2fr/19349555
•Bot waits for calendar to load
•Monitors DOM for available dates
•Uses human-like behavior while waiting
•Instantly clicks when date becomes available
Step 7: Confirmation Page
Pending
•Bot clicks on Confirm to lock the appointment
•Redirects to payment page
Step 8: Stop at Payment
Pending
•Bot stops
•Manual payment required
•Does not proceed beyond this point
Human-like Behavior Notes:
•Scroll idle/randomly every few seconds
•Delay between clicks to mimic human timing
•Monitor and detect DOM changes to identify available appointment dates
