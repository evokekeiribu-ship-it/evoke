require('dotenv').config();
const { GoogleGenAI } = require('@google/genai');

// mock lineWorksApi globally so index.js uses it
const mockLineWorksApi = {
    sendTextMessage: async (userId, text) => {
        console.log(`[MOCK SEND TO ${userId}]:\n${text}\n`);
    },
    sendFileMessage: async (userId, path, filename) => {
        console.log(`[MOCK SEND FILE TO ${userId}]: ${filename}`);
    }
};

const proxyquire = require('proxyquire');
const index = proxyquire('./index', {
    './lineWorksApi': mockLineWorksApi
});

async function run() {
    console.log("Starting simulation...");
    const userId = "test_user";

    // Inject initial state
    const userStates = require('./index').__get__ ? require('./index').__get__('userStates') : null;
    // Actually we can't easily grab un-exported variables unless we modify index.js or use rewire.
    // Let's just simulate the full flow:
    // 1. send "請求書"
    // 2. send image
    // 3. send correction
}
run();
