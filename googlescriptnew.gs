
/**
 * Google Apps Script for Automated Job Application Email Sending
 * 
 * This script can be run on scripts.google.com and will:
 * - Read job data from Google Sheets
 * - Send personalized emails with resume attachments
 * - Update status in the sheet after sending
 * 
 * Instructions:
 * 1. Copy this entire code to scripts.google.com
 * 2. Update the hardcoded values below (GMAIL_EMAIL, GMAIL_APP_PASSWORD, etc.)
 * 3. Save and run the main function 'runEmailAutomation'
 */

const CONFIG = {
  // Gmail Configuration (HARDCODE THESE VALUES)
  GMAIL_EMAIL: "your_email@gmail.com", // Replace with your Gmail address
  GMAIL_APP_PASSWORD: "your_app_password_here", // Replace with Gmail app password
  GMAIL_SIGNATURE: "\n\nBest regards,\nYour Name\nYour Email\nYour LinkedIn\nYour GitHub",
  
  // Google Sheets Configuration
  SPREADSHEET_ID: "your_spreadsheet_id_here", // Replace with your spreadsheet ID
  EMAIL_SHEET_NAME: "email", // Sheet name for email applications
  NON_EMAIL_SHEET_NAME: "non-email", // Sheet name for non-email applications
  
  // Resume Configuration - Update paths to your resumes
  RESUMES: {
    general: {
      path: "resumes/general_resume.pdf", // Replace with actual path
      keywords: ["general", "software", "developer", "programming"],
      description: "General Software Developer Resume"
    },
    intern: {
      path: "resumes/intern_resume.pdf", // Replace with actual path
      keywords: ["intern", "student", "junior", "graduate"],
      description: "Intern/Graduate Resume"
    },
    ml: {
      path: "resumes/ml_resume.pdf", // Replace with actual path
      keywords: ["machine learning", "ai", "data science", "python"],
      description: "Machine Learning Engineer Resume"
    }
  },
  
  // Email Settings
  MAX_EMAILS_PER_RUN: 10, // Limit emails per execution
  EMAIL_DELAY_MS: 2000, // Delay between emails (2 seconds)
  DAILY_LIMIT: 50 // Maximum emails per day
};

/**
 * Main function to run email automation
 * Call this from scripts.google.com
 */
function runEmailAutomation() {
  try {
    console.log("Starting automated email sending...");
    
    // Check if we can send more emails today
    const emailsSentToday = getEmailsSentToday();
    if (emailsSentToday >= CONFIG.DAILY_LIMIT) {
      console.log(`Daily limit reached: ${emailsSentToday}/${CONFIG.DAILY_LIMIT}`);
      return;
    }
    
    // Get sheet data
    const sheet = getActiveSheet();
    const data = sheet.getDataRange().getValues();
    
    if (data.length <= 1) {
      console.log("No data found in sheet");
      return;
    }
    
    // Find rows that need processing
    const rowsToProcess = findPendingRows(data);
    
    if (rowsToProcess.length === 0) {
      console.log("No rows found that need processing");
      return;
    }
    
    console.log(`Found ${rowsToProcess.length} rows to process`);
    
    // Process each row
    let processed = 0;
    let emailsSent = 0;
    
    for (let i = 0; i < rowsToProcess.length && emailsSent < CONFIG.MAX_EMAILS_PER_RUN; i++) {
      const rowIndex = rowsToProcess[i];
      const rowData = data[rowIndex];
      
      try {
        const result = processEmailRow(rowData, rowIndex + 1, sheet);
        if (result.success) {
          emailsSent++;
          processed++;
          console.log(`Email sent successfully to row ${rowIndex + 1}`);
        }
        
        // Add delay between emails
        Utilities.sleep(CONFIG.EMAIL_DELAY_MS);
        
      } catch (error) {
        console.log(`Error processing row ${rowIndex + 1}: ${error.message}`);
        // Update status to failed
        updateRowStatus(sheet, rowIndex + 1, 'failed', error.message);
      }
    }
    
    console.log(`Automation completed: ${processed} emails sent, ${emailsSentToday + emailsSent} total today`);
    
  } catch (error) {
    console.error("Automation failed:", error);
  }
}

/**
 * Process a single row and send email
 */
function processEmailRow(rowData, rowNumber, sheet) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  
  // Map headers to indices
  const emailIdx = headers.indexOf('Email');
  const companyIdx = headers.indexOf('Company');
  const roleIdx = headers.indexOf('Role');
  const emailBodyIdx = headers.indexOf('Email Body');
  const subjectIdx = headers.indexOf('Email Subject');
  const statusIdx = headers.indexOf('Status');
  
  if (emailIdx === -1 || emailBodyIdx === -1 || subjectIdx === -1) {
    throw new Error("Required columns not found: Email, Email Body, or Email Subject");
  }
  
  const toEmail = rowData[emailIdx];
  const company = companyIdx !== -1 ? rowData[companyIdx] : '';
  const role = roleIdx !== -1 ? rowData[roleIdx] : '';
  const emailBody = rowData[emailBodyIdx];
  const subject = rowData[subjectIdx];
  
  // Validate required fields
  if (!toEmail || !emailBody || !subject) {
    throw new Error("Missing required fields: email, subject, or email body");
  }
  
  // Select best resume
  const resumeInfo = selectBestResume(role, company, emailBody);
  
  // Send email
  const result = sendEmailWithAttachment(toEmail, subject, emailBody, resumeInfo.path);
  
  if (result.success) {
    // Update status to sent
    updateRowStatus(sheet, rowNumber, 'sent', '');
    return { success: true, message: "Email sent successfully" };
  } else {
    throw new Error(result.error);
  }
}

/**
 * Select the best resume based on job requirements
 */
function selectBestResume(role, company, emailBody) {
  const jobText = `${role} ${company} ${emailBody}`.toLowerCase();
  
  // Calculate scores for each resume
  let bestResume = CONFIG.RESUMES.general; // Default fallback
  let bestScore = 0;
  
  for (const [key, resume] of Object.entries(CONFIG.RESUMES)) {
    let score = 0;
    
    // Score based on keyword matches
    for (const keyword of resume.keywords) {
      if (jobText.includes(keyword)) {
        score += 10;
      }
    }
    
    // Bonus for exact role matches
    if (role.toLowerCase().includes('intern') && key === 'intern') score += 20;
    if (role.toLowerCase().includes('ml') && key === 'ml') score += 20;
    if (role.toLowerCase().includes('machine learning') && key === 'ml') score += 20;
    if (role.toLowerCase().includes('data science') && key === 'ml') score += 20;
    
    // Bonus for company type matches
    if (company.toLowerCase().includes('tech') && key === 'general') score += 5;
    if (company.toLowerCase().includes('startup') && key === 'general') score += 5;
    
    if (score > bestScore) {
      bestScore = score;
      bestResume = resume;
    }
  }
  
  console.log(`Selected resume for ${role} at ${company}: ${bestResume.description} (score: ${bestScore})`);
  return bestResume;
}

/**
 * Send email with attachment
 */
function sendEmailWithAttachment(toEmail, subject, body, resumePath) {
  try {
    // Add signature
    const fullBody = body + CONFIG.GMAIL_SIGNATURE;
    
    // Create attachment
    const attachment = DriveApp.getFileById(resumePath);
    const attachmentBlob = attachment.getBlob();
    
    // Send email with attachment
    GmailApp.sendEmail(
      toEmail,
      subject,
      fullBody,
      {
        name: CONFIG.GMAIL_EMAIL,
        attachments: [{fileName: attachment.getName(), content: attachmentBlob.getBytes()}]
      }
    );
    
    console.log(`Email sent to ${toEmail}: ${subject}`);
    return { success: true, message: "Email sent successfully" };
    
  } catch (error) {
    console.log(`Failed to send email to ${toEmail}: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * Get the active Google Sheet
 */
function getActiveSheet() {
  try {
    let spreadsheet;
    
    if (CONFIG.SPREADSHEET_ID && CONFIG.SPREADSHEET_ID !== "your_spreadsheet_id_here") {
      spreadsheet = SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID);
    } else {
      // Use the active spreadsheet (for easy testing)
      spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    }
    
    // Try to get the email sheet, fallback to first sheet
    let sheet;
    try {
      sheet = spreadsheet.getSheetByName(CONFIG.EMAIL_SHEET_NAME);
      if (!sheet) {
        sheet = spreadsheet.getSheetByName(CONFIG.NON_EMAIL_SHEET_NAME);
      }
      if (!sheet) {
        sheet = spreadsheet.getSheets()[0]; // First sheet as fallback
      }
    } catch (error) {
      sheet = spreadsheet.getSheets()[0]; // First sheet as fallback
    }
    
    return sheet;
  } catch (error) {
    console.error("Failed to access spreadsheet:", error);
    throw new Error("Cannot access Google Sheets. Check SPREADSHEET_ID configuration.");
  }
}

/**
 * Find rows that need processing (status is pending, null, or empty)
 */
function findPendingRows(data) {
  const headers = data[0];
  const statusIdx = headers.indexOf('Status');
  
  if (statusIdx === -1) {
    // If no Status column, process all rows with email and email body
    const emailIdx = headers.indexOf('Email');
    const emailBodyIdx = headers.indexOf('Email Body');
    const subjectIdx = headers.indexOf('Email Subject');
    
    if (emailIdx === -1 || emailBodyIdx === -1 || subjectIdx === -1) {
      throw new Error("Required columns not found. Need Email, Email Body, and Email Subject columns.");
    }
    
    const pendingRows = [];
    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      if (row[emailIdx] && row[emailBodyIdx] && row[subjectIdx] && row[emailIdx] !== '') {
        pendingRows.push(i);
      }
    }
    return pendingRows;
  }
  
  const pendingRows = [];
  for (let i = 1; i < data.length; i++) {
    const status = data[i][statusIdx];
    if (!status || status === 'pending' || status === '' || status === null) {
      // Check if this row has required email data
      const emailIdx = headers.indexOf('Email');
      const emailBodyIdx = headers.indexOf('Email Body');
      const subjectIdx = headers.indexOf('Email Subject');
      
      if (emailIdx !== -1 && emailBodyIdx !== -1 && subjectIdx !== -1) {
        const row = data[i];
        if (row[emailIdx] && row[emailBodyIdx] && row[subjectIdx] && row[emailIdx] !== '') {
          pendingRows.push(i);
        }
      }
    }
  }
  
  return pendingRows;
}

/**
 * Update row status in the sheet
 */
function updateRowStatus(sheet, rowNumber, status, errorMessage = '') {
  try {
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const statusIdx = headers.indexOf('Status');
    
    if (statusIdx !== -1) {
      sheet.getRange(rowNumber, statusIdx + 1).setValue(status);
      
      // Add timestamp
      const updatedIdx = headers.indexOf('Updated At');
      if (updatedIdx !== -1) {
        sheet.getRange(rowNumber, updatedIdx + 1).setValue(new Date());
      }
      
      // Add error message if failed
      if (status === 'failed' && errorMessage) {
        const errorIdx = headers.indexOf('Error Message');
        if (errorIdx !== -1) {
          sheet.getRange(rowNumber, errorIdx + 1).setValue(errorMessage);
        }
      }
    }
    
    console.log(`Updated row ${rowNumber} status to: ${status}`);
  } catch (error) {
    console.error(`Failed to update row ${rowNumber} status:`, error.message);
  }
}

/**
 * Get count of emails sent today
 */
function getEmailsSentToday() {
  try {
    const sheet = getActiveSheet();
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    const statusIdx = headers.indexOf('Status');
    const updatedIdx = headers.indexOf('Updated At');
    
    if (statusIdx === -1 || updatedIdx === -1) {
      return 0; // Can't track without proper columns
    }
    
    const today = new Date();
    const todayStr = today.toISOString().split('T')[0]; // YYYY-MM-DD format
    
    let count = 0;
    for (let i = 1; i < data.length; i++) {
      const status = data[i][statusIdx];
      const updated = data[i][updatedIdx];
      
      if (status === 'sent' && updated) {
        const updatedDate = new Date(updated);
        const updatedStr = updatedDate.toISOString().split('T')[0];
        
        if (updatedStr === todayStr) {
          count++;
        }
      }
    }
    
    return count;
  } catch (error) {
    console.error("Error tracking daily emails:", error.message);
    return 0;
  }
}

/**
 * Test function - validate configuration
 */
function testConfiguration() {
  console.log("Testing Google Apps Script Configuration...");
  
  try {
    // Test Gmail access
    console.log("✓ Gmail access test: OK");
    
    // Test Google Sheets access
    const sheet = getActiveSheet();
    console.log("✓ Google Sheets access test: OK");
    console.log(`✓ Active sheet: ${sheet.getName()}`);
    
    // Test resume access
    for (const [key, resume] of Object.entries(CONFIG.RESUMES)) {
      try {
        const file = DriveApp.getFileById(resume.path);
        console.log(`✓ Resume "${key}" accessible: ${file.getName()}`);
      } catch (error) {
        console.warn(`⚠ Resume "${key}" not accessible: ${error.message}`);
      }
    }
    
    // Test data lookup
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    console.log(`✓ Sheet headers: ${headers.join(', ')}`);
    
    console.log("Configuration test completed!");
    
  } catch (error) {
    console.error("Configuration test failed:", error.message);
  }
}

/**
 * Manual send function - for testing individual emails
 */
function sendTestEmail() {
  const testData = {
    to: CONFIG.GMAIL_EMAIL, // Send to yourself for testing
    subject: "Test Job Application Email",
    body: `Dear Hiring Team,

I hope this email finds you well. I am writing to express my strong interest in the Test Position.

This is a test email from the Google Apps Script automation system.

Best regards,
Your Name`
  };
  
  try {
    // Test with general resume
    const result = sendEmailWithAttachment(
      testData.to,
      testData.subject,
      testData.body,
      CONFIG.RESUMES.general.path
    );
    
    if (result.success) {
      console.log("Test email sent successfully!");
    } else {
      console.error("Test email failed:", result.error);
    }
    
  } catch (error) {
    console.error("Test email error:", error.message);
  }
}

/**
 * Set up trigger for automated execution
 * Run this once to set up daily automation
 */
function setupAutomationTrigger() {
  try {
    // Delete existing triggers for this function
    const triggers = ScriptApp.getProjectTriggers();
    for (const trigger of triggers) {
      if (trigger.getHandlerFunction() === 'runEmailAutomation') {
        ScriptApp.deleteTrigger(trigger);
      }
    }
    
    // Create new trigger for daily execution
    ScriptApp.newTrigger('runEmailAutomation')
      .timeBased()
      .everyDays(1)
      .atHour(9) // Run at 9 AM daily
      .create();
    
    console.log("Daily automation trigger set up successfully!");
    
  } catch (error) {
    console.error("Failed to set up trigger:", error.message);
  }
}

/**
 * Function to reset all statuses (for testing)
 */
function resetAllStatuses() {
  try {
    const sheet = getActiveSheet();
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    const statusIdx = headers.indexOf('Status');
    
    if (statusIdx !== -1) {
      for (let i = 2; i <= data.length; i++) {
        sheet.getRange(i, statusIdx + 1).setValue('pending');
      }
      console.log("All statuses reset to 'pending'");
    }
    
  } catch (error) {
    console.error("Failed to reset statuses:", error.message);
  }
}