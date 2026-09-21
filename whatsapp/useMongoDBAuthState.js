/**
 * MongoDB Auth State for Baileys
 * 
 * Drop-in replacement for useMultiFileAuthState that stores
 * auth credentials in MongoDB instead of the filesystem.
 */

const { MongoClient } = require('mongodb');
const { proto } = require('@whiskeysockets/baileys');
const { initAuthCreds, BufferJSON } = require('@whiskeysockets/baileys');

const MONGO_URI = process.env.MONGO_URI;
const DB_NAME = process.env.DB_NAME || 'sneakerheads';
const COLLECTION_NAME = process.env.AUTH_COLLECTION || 'baileys_auth_2347066499537';

let mongoClient = null;

async function getMongoClient() {
    if (!mongoClient) {
        if (!MONGO_URI) {
            throw new Error('[MongoDB Auth] MONGO_URI environment variable is not set!');
        }

        const MAX_RETRIES = 5;
        const BASE_DELAY_MS = 3000;

        for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
            try {
                mongoClient = new MongoClient(MONGO_URI);
                await mongoClient.connect();
                console.log('[MongoDB Auth] Connected successfully to MongoDB');
                return mongoClient;
            } catch (err) {
                mongoClient = null;
                if (attempt === MAX_RETRIES) {
                    console.error(`[MongoDB Auth] Failed to connect after ${MAX_RETRIES} attempts:`, err.message);
                    throw err;
                }
                const delay = BASE_DELAY_MS * Math.pow(2, attempt - 1);
                console.warn(`[MongoDB Auth] Connection attempt ${attempt}/${MAX_RETRIES} failed: ${err.message}`);
                console.warn(`[MongoDB Auth] Retrying in ${delay / 1000}s...`);
                await new Promise(resolve => setTimeout(resolve, delay));
            }
        }
    }
    return mongoClient;
}

async function closeMongoConnection() {
    if (mongoClient) {
        await mongoClient.close();
        mongoClient = null;
        console.log('[MongoDB Auth] Connection closed');
    }
}

async function useMongoDBAuthState() {
    const client = await getMongoClient();
    const collection = client.db(DB_NAME).collection(COLLECTION_NAME);

    const readData = async (key) => {
        try {
            const doc = await collection.findOne({ _id: key });
            if (!doc || !doc.value) return null;
            return JSON.parse(doc.value, BufferJSON.reviver);
        } catch (err) {
            console.error(`[MongoDB Auth] Error reading ${key}:`, err.message);
            return null;
        }
    };

    const writeData = async (key, data) => {
        try {
            const value = JSON.stringify(data, BufferJSON.replacer);
            await collection.updateOne(
                { _id: key },
                { $set: { value, updatedAt: new Date() } },
                { upsert: true }
            );
        } catch (err) {
            console.error(`[MongoDB Auth] Error writing ${key}:`, err.message);
        }
    };

    const removeData = async (key) => {
        try {
            await collection.deleteOne({ _id: key });
        } catch (err) {
            console.error(`[MongoDB Auth] Error removing ${key}:`, err.message);
        }
    };

    const credsData = await readData('creds');
    const creds = credsData || initAuthCreds();

    return {
        state: {
            creds,
            keys: {
                get: async (type, ids) => {
                    const data = {};
                    await Promise.all(
                        ids.map(async (id) => {
                            const key = `${type}-${id}`;
                            let value = await readData(key);
                            if (type === 'app-state-sync-key' && value) {
                                value = proto.Message.AppStateSyncKeyData.fromObject(value);
                            }
                            data[id] = value;
                        })
                    );
                    return data;
                },
                set: async (data) => {
                    const tasks = [];
                    for (const category in data) {
                        for (const id in data[category]) {
                            const value = data[category][id];
                            const key = `${category}-${id}`;
                            tasks.push(
                                value ? writeData(key, value) : removeData(key)
                            );
                        }
                    }
                    await Promise.all(tasks);
                }
            }
        },
        saveCreds: async () => {
            await writeData('creds', creds);
        }
    };
}

async function clearMongoAuth() {
    const client = await getMongoClient();
    const collection = client.db(DB_NAME).collection(COLLECTION_NAME);
    try {
        const result = await collection.deleteMany({});
        console.log(`[MongoDB Auth] Cleared ${result.deletedCount} old auth documents.`);
    } catch (err) {
        console.error(`[MongoDB Auth] Error clearing auth:`, err.message);
    }
}

module.exports = { useMongoDBAuthState, closeMongoConnection, clearMongoAuth, getMongoClient };
