const env = require('dotenv').config({ path: __dirname + '/../.env' }).parsed || {};
const msg = process.argv.slice(2).join(' ');
(async () => {
  if (env.TELEGRAM_BOT_TOKEN && env.TELEGRAM_CHAT_ID) {
    const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text: msg })
    });
    console.log('telegram:', (await r.json()).ok ? 'sent' : 'FAILED');
  } else if (env.GMAIL_USER && env.GMAIL_APP_PASSWORD) {
    const nodemailer = require('nodemailer');
    const tx = nodemailer.createTransport({ service: 'gmail', auth: { user: env.GMAIL_USER, pass: env.GMAIL_APP_PASSWORD } });
    await tx.sendMail({ from: env.GMAIL_USER, to: env.GMAIL_USER, subject: 'TradingView brief', text: msg });
    console.log('gmail: sent');
  } else {
    console.log('NO CHANNEL CONFIGURED — printing:\n' + msg);
  }
})();
