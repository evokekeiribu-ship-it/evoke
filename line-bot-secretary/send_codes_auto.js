require('dotenv').config();
const line = require('@line/bot-sdk');

const config = {
    channelAccessToken: process.env.LINE_CHANNEL_ACCESS_TOKEN,
    channelSecret: process.env.LINE_CHANNEL_SECRET
};
const client = new line.messagingApi.MessagingApiClient(config);

async function send() {
    try {
        const realUserId = "U271592e02ec59829d590590021916744";
        const messageText = `【抽出結果】
XQFXQVLHWTG5QPCN (10,000円)
XC3GQ39WDLK3TKMT (20,000円)
XY2DH85N532KCW4N (10,000円)
XNZ2K29GRWCW2KV8 (50,000円)
X4FLRC8V28QKPXNF (48,000円)
XHYZL4H6KXTW3RDT (250,000円)
XDPRF6PMYFYCZV5Q (10,000円)

合計金額: 398,000円`;

        await client.pushMessage({
            to: realUserId,
            messages: [{
                type: 'text',
                text: messageText
            }]
        });
        console.log("Success");
    } catch (e) {
        console.error(e);
    }
}
send();
