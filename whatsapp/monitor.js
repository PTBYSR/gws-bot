/**
 * WhatsApp Baileys Monitor
 * 
 * Cloned and adapted from sakura-labs/sneakerheads architecture.
 * Connects to WhatsApp using pairing code for number: 2347066499537
 * Stores session auth state and monitored messages in MongoDB.
 */

require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });
const { default: makeWASocket, DisconnectReason, fetchLatestBaileysVersion, downloadMediaMessage } = require('@whiskeysockets/baileys');
const { useMongoDBAuthState, closeMongoConnection, clearMongoAuth, getMongoClient } = require('./useMongoDBAuthState');
const pino = require('pino');
const express = require('express');
const fs = require('fs');
const path = require('path');

// Ensure downloads directory exists
const DOWNLOADS_DIR = path.join(__dirname, 'downloads');
if (!fs.existsSync(DOWNLOADS_DIR)) {
    fs.mkdirSync(DOWNLOADS_DIR, { recursive: true });
}

// Configuration
const HTTP_PORT = process.env.PORT || 3005;
const DB_NAME = process.env.DB_NAME || 'sneakerheads';
const MONITOR_COLLECTION = process.env.MONITOR_COLLECTION || 'monitored_messages';
const BOT_PHONE_NUMBER = process.env.BOT_PHONE_NUMBER || '2347066499537';

let db = null;
let monitoredCollection = null;

// Connect to MongoDB for logging messages
async function initMessageDb() {
    try {
        const client = await getMongoClient();
        db = client.db(DB_NAME);
        monitoredCollection = db.collection(MONITOR_COLLECTION);
        console.log(`[DB] Connected to MongoDB. Logging messages to: ${DB_NAME}.${MONITOR_COLLECTION}`);
    } catch (e) {
        console.error("[DB] MongoDB Connection Error for message log:", e.message);
    }
}

// Extract pure phone number or JID type
function extractPhone(jid) {
    if (!jid) return null;
    if (jid.includes('@lid')) return jid;
    return jid.replace(/@.*$/, '').replace(/^\+/, '').replace(/\D/g, '');
}

// Extract text and media metadata from Baileys message object
function parseMessage(msg) {
    const messageContent = msg.message;
    if (!messageContent) return null;

    let text = null;
    let type = 'unknown';
    let mediaInfo = null;

    // Determine type and extract text
    if (messageContent.conversation) {
        text = messageContent.conversation;
        type = 'text';
    } else if (messageContent.extendedTextMessage?.text) {
        text = messageContent.extendedTextMessage.text;
        type = 'text';
    } else if (messageContent.imageMessage) {
        text = messageContent.imageMessage.caption || '';
        type = 'image';
        mediaInfo = {
            mimetype: messageContent.imageMessage.mimetype,
            height: messageContent.imageMessage.height,
            width: messageContent.imageMessage.width
        };
    } else if (messageContent.videoMessage) {
        text = messageContent.videoMessage.caption || '';
        type = 'video';
        mediaInfo = {
            mimetype: messageContent.videoMessage.mimetype,
            duration: messageContent.videoMessage.seconds
        };
    } else if (messageContent.documentMessage) {
        text = messageContent.documentMessage.caption || '';
        type = 'document';
        mediaInfo = {
            mimetype: messageContent.documentMessage.mimetype,
            fileName: messageContent.documentMessage.fileName
        };
    } else if (messageContent.audioMessage) {
        type = 'audio';
        mediaInfo = {
            mimetype: messageContent.audioMessage.mimetype,
            duration: messageContent.audioMessage.seconds
        };
    } else if (messageContent.protocolMessage) {
        type = 'protocol';
    } else if (messageContent.senderKeyDistributionMessage) {
        type = 'sender_key_distribution';
    }

    // Extract quoted context if any
    let quotedText = null;
    let quotedSender = null;
    const contextInfo = messageContent.extendedTextMessage?.contextInfo || 
                        messageContent.imageMessage?.contextInfo ||
                        messageContent.videoMessage?.contextInfo;
                        
    if (contextInfo?.quotedMessage) {
        const quotedMsg = contextInfo.quotedMessage;
        quotedSender = contextInfo.participant;
        if (quotedMsg.conversation) quotedText = quotedMsg.conversation;
        else if (quotedMsg.extendedTextMessage?.text) quotedText = quotedMsg.extendedTextMessage.text;
    }

    return { text, type, mediaInfo, quotedText, quotedSender };
}

const logger = pino({ level: 'silent' });
let globalSock = null;

// Start Express HTTP Server
function startHttpServer() {
    const app = express();
    app.use(express.json());

    // Base endpoint
    app.get('/', (req, res) => {
        res.send('Bot is running passively!');
    });

    // Health check endpoint
    app.get('/health', (req, res) => {
        res.json({
            status: 'ok',
            connected: globalSock !== null,
            monitored_number: BOT_PHONE_NUMBER,
            db_connected: db !== null
        });
    });

    // Query logs endpoint
    app.get('/messages', async (req, res) => {
        if (!monitoredCollection) {
            return res.status(503).json({ error: 'Database not initialized' });
        }

        try {
            const limit = parseInt(req.query.limit) || 100;
            const phone = req.query.phone;
            const query = {};
            
            if (phone) {
                query.$or = [
                    { senderPhone: phone },
                    { recipientPhone: phone }
                ];
            }

            const messages = await monitoredCollection
                .find(query)
                .sort({ timestamp: -1 })
                .limit(limit)
                .toArray();

            res.json({ count: messages.length, messages });
        } catch (error) {
            res.status(500).json({ error: error.message });
        }
    });

    // Send a message endpoint (tooling helper)
    app.post('/send', async (req, res) => {
        const { to, message, imagePath } = req.body;

        if (!globalSock) {
            return res.status(503).json({ error: 'WhatsApp not connected' });
        }

        if (!to || (!message && !imagePath)) {
            return res.status(400).json({ error: 'Recipient ("to") and either "message" or "imagePath" are required' });
        }

        try {
            const recipientJid = to.includes('@') ? to : `${to}@s.whatsapp.net`;
            let messageBody;

            if (imagePath) {
                if (fs.existsSync(imagePath)) {
                    messageBody = { image: { url: imagePath }, caption: message || '' };
                } else {
                    return res.status(400).json({ error: `Image file not found at: ${imagePath}` });
                }
            } else {
                messageBody = { text: message };
            }

            const sent = await globalSock.sendMessage(recipientJid, messageBody);
            res.json({ success: true, messageId: sent.key.id });
        } catch (error) {
            res.status(500).json({ error: error.message });
        }
    });

    app.listen(HTTP_PORT, () => {
        console.log(`📡 Monitor REST API running on port ${HTTP_PORT}`);
        console.log(`   GET  /health     - Check monitor status`);
        console.log(`   GET  /messages   - Query monitored messages`);
        console.log(`   POST /send       - Send WhatsApp message using this instance\n`);
    });
}

// Start WhatsApp connection
async function startMonitor() {
    const { state, saveCreds } = await useMongoDBAuthState();

    let version;
    try {
        const versionInfo = await fetchLatestBaileysVersion();
        version = versionInfo.version;
        console.log(`📦 Using WA Web version: ${version.join('.')}`);
    } catch (err) {
        console.warn('⚠️  Could not fetch latest version, using default');
        version = [2, 3000, 1015901307];
    }

    const browserConfig = ['Mac OS', 'Safari', '10.15.7'];
    let pairingCodeRequested = false;

    const sock = makeWASocket({
        auth: state,
        version: version,
        printQRInTerminal: false,
        logger: logger,
        browser: browserConfig,
        connectTimeoutMs: 60000,
        keepAliveIntervalMs: 10000,
        emitOwnEvents: true,
        retryRequestDelayMs: 250,
        syncFullHistory: false
    });

    globalSock = sock;

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect } = update;

        if (connection === 'connecting' && !sock.authState.creds.registered && !pairingCodeRequested) {
            pairingCodeRequested = true;
            setTimeout(async () => {
                try {
                    console.log(`\n📞 Requesting pairing code for ${BOT_PHONE_NUMBER}...`);
                    const code = await sock.requestPairingCode(BOT_PHONE_NUMBER);
                    console.log(`\n========================================`);
                    console.log(`📢 YOUR WHATSAPP PAIRING CODE: ${code}`);
                    console.log(`========================================`);
                    console.log('👉 Go to WhatsApp > Linked Devices > Link a Device > Link with phone number instead\n');
                } catch (err) {
                    console.error('Failed to request pairing code:', err);
                    pairingCodeRequested = false;
                }
            }, 3000);
        }

        if (connection === 'open') {
            console.clear();
            const actualNumber = sock.user.id.split(':')[0];
            console.log('========================================');
            console.log('✅ MONITOR IS ACTIVE!');
            console.log(`📱 Connected as: +${actualNumber}`);
            console.log(`📡 API Port: ${HTTP_PORT}`);
            console.log(`🗄️  Logging to MongoDB: ${DB_NAME}.${MONITOR_COLLECTION}`);
            console.log('========================================\n');
        }

        if (connection === 'close') {
            globalSock = null;
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

            console.log(`\n🔍 Connection closed: ${statusCode}`);

            if (statusCode === DisconnectReason.loggedOut || statusCode === 401) {
                console.log('👋 Session invalid (Logged out/401). Clearing auth to generate a new pairing code...');
                clearMongoAuth().then(() => {
                    console.log('✅ Auth cleared! Please restart the script to generate a new pairing code.');
                    process.exit(0);
                });
            } else if (statusCode === 440) {
                console.log('⚠️  Conflict (440): Another session is active or auth is out of sync.');
                console.log('If this persists, you may need to clear your MongoDB auth collection.');
                console.log('♻️  Reconnecting in 5 seconds...');
                setTimeout(() => startMonitor().catch(console.error), 5000);
            } else if (shouldReconnect) {
                console.log('♻️  Reconnecting in 2 seconds...');
                setTimeout(() => startMonitor().catch(console.error), 2000);
            } else {
                console.log('👋 Logged out. Delete database credentials to re-pair.');
            }
        }
    });

    sock.ev.on('creds.update', saveCreds);

    // Monitor incoming/outgoing messages
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        if (type !== 'notify' && type !== 'append') return;

        for (const msg of messages) {
            try {
                // Determine sender and check if it's incoming
                const fromMe = msg.key.fromMe || false;
                const senderJid = msg.key.remoteJid;

                // Skip status broadcasts
                if (senderJid === 'status@broadcast') continue;

                // Parse message details
                const parsed = parseMessage(msg);
                if (!parsed) continue;

                const senderPhone = extractPhone(senderJid);
                const senderName = msg.pushName || 'Unknown';
                const messageId = msg.key.id;
                const timestamp = new Date((msg.messageTimestamp || Math.floor(Date.now() / 1000)) * 1000);

                // Check for media attachment to download
                let mediaPath = null;
                const isMedia = msg.message?.imageMessage || msg.message?.videoMessage || msg.message?.documentMessage || msg.message?.audioMessage;
                
                if (isMedia) {
                    try {
                        console.log(`[Media] Downloading media from ${senderName} (+${senderPhone})...`);
                        const buffer = await downloadMediaMessage(msg, 'buffer', {}, { logger });
                        if (buffer) {
                            const ext = parsed.mediaInfo?.mimetype?.split('/')[1]?.split(';')[0] || 'bin';
                            const filename = `${messageId}_${senderPhone || 'self'}.${ext}`;
                            const fullPath = path.join(DOWNLOADS_DIR, filename);
                            fs.writeFileSync(fullPath, buffer);
                            mediaPath = fullPath;
                            console.log(`[Media] Saved attachment to ${mediaPath}`);
                        }
                    } catch (mediaErr) {
                        console.error(`[Media Error] Failed to download/save attachment: ${mediaErr.message}`);
                    }
                }

                // Format console output
                const directionStr = fromMe ? 'OUTGOING' : 'INCOMING';
                const timeStr = timestamp.toLocaleTimeString('en-US', { hour12: false });
                const dateStr = timestamp.toLocaleDateString();
                const logLabel = `[${dateStr} ${timeStr}] [${directionStr}]`;

                console.log(`${logLabel} Chat: ${senderPhone} (${senderName})`);
                if (parsed.text) {
                    console.log(`   Message: "${parsed.text}"`);
                }
                if (parsed.quotedText) {
                    console.log(`   Quoting: "${parsed.quotedText}"`);
                }
                if (parsed.type && parsed.type !== 'text') {
                    console.log(`   Type: ${parsed.type} ${mediaPath ? `(Saved: ${path.basename(mediaPath)})` : ''}`);
                }
                console.log('--------------------------------------------------');

                // Save message details to MongoDB
                if (monitoredCollection) {
                    const messageDoc = {
                        messageId,
                        chatJid: senderJid,
                        senderPhone,
                        senderName,
                        fromMe,
                        direction: directionStr,
                        text: parsed.text,
                        type: parsed.type,
                        mediaInfo: parsed.mediaInfo,
                        mediaPath,
                        quotedText: parsed.quotedText,
                        quotedSender: parsed.quotedSender,
                        timestamp,
                        rawMessage: msg,
                        createdAt: new Date()
                    };

                    await monitoredCollection.updateOne(
                        { messageId },
                        { $setOnInsert: messageDoc },
                        { upsert: true }
                    );
                }

            } catch (err) {
                console.error(`[Error] Failed to process message in monitor: ${err.message}`);
            }
        }
    });

    console.log('🚀 Initializing Monitor connection...');
}

// Graceful shutdown
const gracefulShutdown = async (signal) => {
    console.log(`\n[Shutdown] Received signal ${signal}. Cleaning up...`);
    try {
        await closeMongoConnection();
    } catch (err) {
        console.error('[Shutdown Error]', err.message);
    }
    process.exit(0);
};

process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));

// Start it up
(async () => {
    await initMessageDb();
    startHttpServer();
    await startMonitor();
})().catch(console.error);
