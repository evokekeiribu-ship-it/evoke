require('dotenv').config();
const line = require('@line/bot-sdk');

const config = {
    channelAccessToken: process.env.LINE_CHANNEL_ACCESS_TOKEN,
    channelSecret: process.env.LINE_CHANNEL_SECRET
};

const client = new line.messagingApi.MessagingApiClient(config);

async function sendCodes() {
    try {
        const realUserId = "U271592e02ec59829d590590021916744";
        const messageText = `XDPRF6PMYFYCZV5Q\nXG6VL28LGD2FXD6Y\nXQ4NJM26XWZ4XKV3\nX6WZ4JH63P6WNXRX\nXTQYK6JM5XGYDCQX\nXXLRG8D3R8XZ3VHW\nXTWX9LDVW4G9W723\nX9LPR8NTXL4LRXLT`;

        await client.pushMessage({
            to: realUserId,
            messages: [{
                type: 'text',
                text: messageText
            }]
        });
        console.log("Success!");
    } catch (e) {
        console.error(e);
    }
}

sendCodes();
