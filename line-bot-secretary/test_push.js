require('dotenv').config();
const line = require('@line/bot-sdk');

const config = {
    channelAccessToken: process.env.LINE_CHANNEL_ACCESS_TOKEN,
    channelSecret: process.env.LINE_CHANNEL_SECRET
};

const client = new line.messagingApi.MessagingApiClient(config);

async function test() {
    try {
        const userId = "U4d0fe7cb05d07567c6acf34bcfe853b8"; // This is actually the bot's destination ID, wait no, let's use the user ID from the logs.
        const realUserId = "U271592e02ec59829d590590021916744";
        const downloadUrl = "https://6050177456d3a8.lhr.life/download/2026-02-23/%E6%A0%AA%E5%BC%8F%E4%BC%9A%E7%A4%BETUYOSHI%E5%BE%A1%E4%B8%AD_20260223_01.pdf";
        console.log("Sending...");
        await client.pushMessage({
            to: realUserId,
            messages: [{
                type: 'file',
                originalContentUrl: downloadUrl,
                fileName: "test.pdf",
                fileSize: 1024 // try with fileSize
            }]
        });
        console.log("Success!");
    } catch (e) {
        if (e.originalError && e.originalError.response) {
            console.error("Error response data:", JSON.stringify(e.originalError.response.data, null, 2));
        } else {
            console.error(e);
        }
    }
}

test();
