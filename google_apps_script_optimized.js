
/**
 * ================================================================
 * 🚀 AI JOB APPLICATION AGENT - USER VERSION (v2.5)
 * ================================================================
 * 
 * INSTRUCTIONS FOR USER:
 * 1. Create a Folder in Google Drive (e.g., named "Job Automation").
 * 2. Upload your Resume PDFs there with descriptive names:
 *    - "Resume_Frontend_React.pdf"
 *    - "Resume_Backend_Python.pdf"
 *    - "Resume_General.pdf"
 * 3. Create "profile.json" in that same folder.
 * 4. Paste this script into Extensions > Apps Script.
 * 5. CONFIGURE API KEYS (Two Options):
 *    - OPTION A (EASY): Paste keys in the CONFIG section below.
 *    - OPTION B (SECURE): Go to Project Settings > Script Properties and add 'OPENROUTER_API_KEYS' (comma separated).
 * 6. Run "setup()" from the menu.
 *
 * ================================================================
 */

// === 1. USER CONFIGURATION (EDIT THIS SECTION ONLY) ===
const CONFIG = {
    // Option A: Paste API Keys here (easiest)
    // If you use Option B (Script Properties), leave this as is or empty.
    OPENROUTER_API_KEYS: ['sk-or-v1-...'],

    // Option B (Secure):
    // The script will AUTOMATICALLY check Script Properties for 'OPENROUTER_API_KEYS' first.

    // Folder Name where you stored profile.json and Resume PDFs
    DRIVE_FOLDER_NAME: 'Job Automation',

    // The filename of your "General Purpose" resume in that folder
    DEFAULT_RESUME: 'Resume_General.pdf',

    // The name the Recruiter sees on the attachment
    SENT_RESUME_NAME: 'Dheeraj_Sharma_Resume.pdf',

    // Script Behavior
    SHEET_NAME: 'email',
    BATCH_SIZE: 5,
    SEND_BATCH_SIZE: 10,

    // AI Models
    MODELS: {
        DRAFT: 'arcee-ai/trinity-large-preview:free',
        EXTRACT: 'google/gemini-2.0-flash-exp:free'
    }
};

// === 2. SYSTEM CONSTANTS ===
const FILES = {
    PROFILE: 'profile.json'
};

const STATUS = {
    PENDING: 'PENDING',
    DRAFTED: 'DRAFTED',
    SENT: 'SENT',
    ERROR: 'ERROR',
    INVALID: 'INVALID_EMAIL'
};

// ================================================================
// === MENU & SETUP
// ================================================================

function onOpen() {
    SpreadsheetApp.getUi()
        .createMenu('🚀 Auto-Apply Agent')
        .addItem('1. 📂 Initialize (Setup Sheets & Files)', 'setup')
        .addSeparator()
        .addItem('2. ✍️ Generate Drafts & Pick Resume', 'generateDrafts')
        .addItem('3. 📤 Send Drafts', 'sendDrafts')
        .addSeparator()
        .addItem('✨ One-Click Sheet Setup', 'setupSheets')
        .addItem('⏰ Start Auto-Pilot', 'createTriggers')
        .addItem('🛑 Stop Auto-Pilot', 'deleteTriggers')
        .addToUi();
}

function setup() {
    const ui = SpreadsheetApp.getUi();
    try {
        // 1. Ensure Sheets exist
        setupSheets(true);

        const profile = loadProfile();
        const resumes = listResumes();

        if (resumes.length === 0) throw new Error("No PDF resumes found in folder '" + CONFIG.DRIVE_FOLDER_NAME + "'");

        if (!resumes.includes(CONFIG.DEFAULT_RESUME)) {
            throw new Error("Default Resume '" + CONFIG.DEFAULT_RESUME + "' not found in folder. Please rename one file to this or update CONFIG.");
        }

        const apiKeys = getApiKeys('OPENROUTER_API_KEYS');
        if (!apiKeys || apiKeys.length === 0 || apiKeys[0].includes('...')) {
            throw new Error("No Valid API Keys found! \nAdd 'OPENROUTER_API_KEYS' to Script Properties OR paste in CONFIG.");
        }

        ui.alert('✅ Setup Successful!\n\n' +
            'Found Profile: ' + profile.personal_information.full_name + '\n' +
            'Default Resume: ' + CONFIG.DEFAULT_RESUME + '\n' +
            'API Keys: Found ' + apiKeys.length + ' key(s).\n\n' +
            'System is ready!');
    } catch (e) {
        ui.alert('❌ Setup Failed:\n' + e.message);
    }
}

// ================================================================
// === SHEET SETUP (ONE-CLICK)
// ================================================================

function setupSheets(silent) {
    const spread = SpreadsheetApp.getActiveSpreadsheet();
    const headers = [
        'Job ID', 'Company Name', 'Job Role', 'Location', 'Eligibility',
        'Contact Email', 'Contact Phone', 'Recruiter Name', 'Application Link',
        'Application Method', 'Job Description', 'Email Subject', 'Email Body',
        'Status', 'Created At', 'Experience Required', 'Job Relevance', 'Resume File'
    ];

    const sheetsToCreate = ['email', 'non-email'];
    let created = 0;

    sheetsToCreate.forEach(name => {
        let sheet = spread.getSheetByName(name);
        if (!sheet) {
            sheet = spread.insertSheet(name);
            sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
            sheet.setFrozenRows(1);
            sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
            created++;
        }
    });

    if (!silent && created > 0) {
        SpreadsheetApp.getUi().alert(`✅ Created ${created} new sheets with headers!`);
    } else if (!silent) {
        SpreadsheetApp.getUi().alert('ℹ️ Sheets "email" and "non-email" already exist.');
    }
}

function createTriggers() {
    deleteTriggers();
    ScriptApp.newTrigger('generateDrafts').timeBased().everyMinutes(15).create();
    ScriptApp.newTrigger('sendDrafts').timeBased().everyHours(1).create();
    SpreadsheetApp.getUi().alert('✅ Auto-Pilot Started!');
}

function deleteTriggers() {
    const triggers = ScriptApp.getProjectTriggers();
    triggers.forEach(t => ScriptApp.deleteTrigger(t));
    SpreadsheetApp.getUi().alert('🛑 Auto-Pilot Stopped.');
}

// ================================================================
// === CORE LOGIC: GENERATE DRAFTS
// ================================================================

function generateDrafts() {
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.SHEET_NAME);
    if (!sheet) return toast("Tab '" + CONFIG.SHEET_NAME + "' not found!");

    const data = sheet.getDataRange().getValues();
    const idx = getHeaderIndex(data[0]);
    if (!idx) return;

    const profile = loadProfile();
    const availableResumes = listResumes();
    let count = 0;

    if (idx.resumeFile === undefined) {
        const lastCol = data[0].length;
        sheet.getRange(1, lastCol + 1).setValue("Resume File");
        idx.resumeFile = lastCol;
    }

    for (let i = 1; i < data.length; i++) {
        if (count >= CONFIG.BATCH_SIZE) break;
        const row = data[i];
        if (row[idx.status] !== STATUS.PENDING && row[idx.status] !== '') continue;

        try {
            const jd = row[idx.jd];
            if (!jd) continue;

            let company = row[idx.company];
            if (!company) {
                const extracted = extractJobDetails(jd);
                if (extracted && extracted.company) {
                    sheet.getRange(i + 1, idx.company + 1).setValue(extracted.company);
                    company = extracted.company;
                }
            }

            // Generate Draft & INTELLIGENTLY Select Resume
            const result = generateEmailAndSelectResume(jd, profile, company, availableResumes);
            if (result) {
                sheet.getRange(i + 1, idx.subject + 1).setValue(result.subject);
                sheet.getRange(i + 1, idx.body + 1).setValue(result.body);

                const chosenResume = result.selectedResume && availableResumes.includes(result.selectedResume)
                    ? result.selectedResume
                    : CONFIG.DEFAULT_RESUME;

                sheet.getRange(i + 1, idx.resumeFile + 1).setValue(chosenResume);

                sheet.getRange(i + 1, idx.status + 1).setValue(STATUS.DRAFTED);
                sheet.getRange(i + 1, idx.created + 1).setValue(new Date());
                count++;
            }
        } catch (e) {
            console.error("Error row " + (i + 1) + ": " + e);
            sheet.getRange(i + 1, idx.status + 1).setValue(STATUS.ERROR + ": " + e.message);
        }
    }
    if (count > 0) toast(`Generated ${count} drafts.`);
}

// ================================================================
// === CORE LOGIC: SEND EMAILS
// ================================================================

function sendDrafts() {
    const hour = new Date().getHours();
    if (hour < 9 || hour > 21) return console.log("Skipping send (Outside hours)");

    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.SHEET_NAME);
    if (!sheet) return;

    const data = sheet.getDataRange().getValues();
    const idx = getHeaderIndex(data[0]);
    if (!idx) return;

    let count = 0;

    for (let i = 1; i < data.length; i++) {
        if (count >= CONFIG.SEND_BATCH_SIZE) break;
        const row = data[i];
        if (row[idx.status] !== STATUS.DRAFTED) continue;

        const email = row[idx.email];
        const subject = row[idx.subject];
        const body = row[idx.body];

        let resumeName = row[idx.resumeFile];
        if (!resumeName || typeof resumeName !== 'string') {
            resumeName = CONFIG.DEFAULT_RESUME;
        }

        if (!isValidEmail(email)) {
            sheet.getRange(i + 1, idx.status + 1).setValue(STATUS.INVALID);
            continue;
        }

        try {
            let resumeFile;
            try {
                resumeFile = getFileByName(resumeName);
            } catch (e) {
                console.warn("Chosen resume '" + resumeName + "' not found. Using Default.");
                resumeFile = getFileByName(CONFIG.DEFAULT_RESUME);
            }

            const resumeBlob = resumeFile.getBlob().setName(CONFIG.SENT_RESUME_NAME);

            GmailApp.sendEmail(email, subject, stripHtml(body), {
                htmlBody: body,
                attachments: [resumeBlob],
                name: CONFIG.NAME
            });

            sheet.getRange(i + 1, idx.status + 1).setValue(STATUS.SENT);
            sheet.getRange(i + 1, idx.created + 1).setValue(new Date());
            count++;
        } catch (e) {
            console.error("Send Failed: " + email + " - " + e);
            sheet.getRange(i + 1, idx.status + 1).setValue(STATUS.ERROR + ": " + e.message);
        }
    }
    if (count > 0) toast(`Sent ${count} emails.`);
}

// ================================================================
// === AI HELPERS (SMART MAPPING)
// ================================================================

function getApiKeys(keyName) {
    // 1. Try Script Properties (Environment Variables)
    const props = PropertiesService.getScriptProperties();
    const envVal = props.getProperty(keyName);

    if (envVal) {
        return envVal.split(',').map(k => k.trim()).filter(Boolean);
    }

    // 2. Fallback to CONFIG (Code)
    const configVal = CONFIG[keyName];
    if (configVal && Array.isArray(configVal) && configVal.length > 0 && !configVal[0].includes('...')) {
        return configVal;
    }

    return [];
}

function generateEmailAndSelectResume(jd, profile, companyName, availableResumes) {
    const prompt = `
    You are an expert career coach.
    
    JOB DESCRIPTION:
    ${jd.substring(0, 3000)}
    
    CANDIDATE PROFILE:
    ${JSON.stringify(profile).substring(0, 3000)}
    
    AVAILABLE RESUME FILES:
    ${JSON.stringify(availableResumes)}
    DEFAULT RESUME: ${CONFIG.DEFAULT_RESUME}
    
    TASK:
    1. ANALYZE the Job Description to identify primary role/skills.
    2. SELECT the most appropriate resume filename from the list.
    3. WRITE a personalized cold email (under 250 words).
    
    OUTPUT JSON:
    {
      "selectedResume": "exact_filename.pdf",
      "subject": "Email Subject",
      "body": "<html> email body..."
    }
  `;

    const response = callLLM(prompt, true);
    try {
        return JSON.parse(response);
    } catch (e) { return null; }
}

function extractJobDetails(jd) {
    const prompt = `Extract JSON: { "company": "...", "email": "...", "role": "..." } from:\n${jd.substring(0, 1000)}`;
    const response = callLLM(prompt, true);
    try { return JSON.parse(response); } catch (e) { return null; }
}

function callLLM(prompt, jsonMode) {
    const keys = getApiKeys('OPENROUTER_API_KEYS');
    if (!keys || keys.length === 0) throw new Error("Missing API Keys.");

    const url = "https://openrouter.ai/api/v1/chat/completions";
    const apiKey = keys[Math.floor(Math.random() * keys.length)]; // Load balance

    const payload = {
        model: CONFIG.MODELS.DRAFT,
        messages: [{ role: "user", content: prompt }],
        response_format: jsonMode ? { type: "json_object" } : undefined
    };
    const options = {
        method: "post", contentType: "application/json", headers: { "Authorization": `Bearer ${apiKey}` },
        payload: JSON.stringify(payload), muteHttpExceptions: true
    };
    const res = UrlFetchApp.fetch(url, options);
    if (res.getResponseCode() !== 200) throw new Error("API Error: " + res.getContentText());
    return JSON.parse(res.getContentText()).choices[0].message.content;
}

// ================================================================
// === FILE SYSTEM HELPERS
// ================================================================

function getDriveFolder() {
    if (!CONFIG.DRIVE_FOLDER_NAME) return DriveApp.getRootFolder();
    const folders = DriveApp.getFoldersByName(CONFIG.DRIVE_FOLDER_NAME);
    if (folders.hasNext()) return folders.next();
    throw new Error(`Folder "${CONFIG.DRIVE_FOLDER_NAME}" not found in Drive.`);
}

function loadProfile() {
    const folder = getDriveFolder();
    const files = folder.getFilesByName(FILES.PROFILE);
    if (!files.hasNext()) throw new Error(`"${FILES.PROFILE}" not found.`);
    return JSON.parse(files.next().getBlob().getDataAsString());
}

function listResumes() {
    const folder = getDriveFolder();
    const files = folder.getFiles();
    const resumes = [];
    while (files.hasNext()) {
        const file = files.next();
        if (file.getMimeType() === 'application/pdf' && file.getName().toLowerCase().includes('resume')) {
            resumes.push(file.getName());
        }
    }
    return resumes;
}

function getFileByName(filename) {
    const folder = getDriveFolder();
    const files = folder.getFilesByName(filename);
    if (files.hasNext()) return files.next();
    // Fallback scan
    const allFiles = folder.getFiles();
    while (allFiles.hasNext()) {
        const f = allFiles.next();
        if (f.getName() === filename) return f;
    }
    throw new Error("File not found: " + filename);
}

// ================================================================
// === UTILS
// ================================================================

function getHeaderIndex(headers) {
    const map = {};
    headers.forEach((h, i) => map[h.toString().trim()] = i);
    return {
        jd: map['Job Description'],
        email: map['Contact Email'],
        subject: map['Email Subject'],
        body: map['Email Body'],
        status: map['Status'],
        company: map['Company Name'],
        role: map['Job Role'],
        created: map['Created At'],
        resumeFile: map['Resume File']
    };
}

function isValidEmail(email) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email); }
function stripHtml(html) { return (html || '').replace(/<[^>]*>/g, ''); }
function toast(msg) { SpreadsheetApp.getActiveSpreadsheet().toast(msg); console.log(msg); }
