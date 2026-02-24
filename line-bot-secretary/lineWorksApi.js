require('dotenv').config();
const axios = require('axios');
const jwt = require('jsonwebtoken');
const fs = require('fs');
const FormData = require('form-data');
const path = require('path');

// OAuthトークンをキャッシュして再利用する仕組み
let cachedToken = null;
let tokenExp = 0;

/**
 * 秘密鍵(JWT)で署名し、LINE WORKS APIから一時アクセストークンを取得する
 */
async function getAccessToken() {
    // トークンが有効期限内の場合はキャッシュを返す（5分前リセット）
    if (cachedToken && Date.now() < tokenExp) {
        return cachedToken;
    }

    const clientId = process.env.LINE_WORKS_CLIENT_ID;
    const clientSecret = process.env.LINE_WORKS_CLIENT_SECRET;
    const serviceAccount = process.env.LINE_WORKS_SERVICE_ACCOUNT;
    const privateKeyPath = path.join(__dirname, 'private.key');
    const privateKey = fs.readFileSync(privateKeyPath, 'utf8');

    const header = { alg: 'RS256', typ: 'JWT' };
    const payload = {
        iss: clientId,
        sub: serviceAccount,
        iat: Math.floor(Date.now() / 1000),
        exp: Math.floor(Date.now() / 1000) + 3600
    };

    // JWT署名
    const token = jwt.sign(payload, privateKey, { header: header });

    // トークン引き換えリクエスト
    const params = new URLSearchParams();
    params.append('grant_type', 'urn:ietf:params:oauth:grant-type:jwt-bearer');
    params.append('assertion', token);
    params.append('client_id', clientId);
    params.append('client_secret', clientSecret);
    params.append('scope', 'bot');

    const response = await axios.post('https://auth.worksmobile.com/oauth2/v2.0/token', params.toString(), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    });

    cachedToken = response.data.access_token;
    tokenExp = Date.now() + ((response.data.expires_in - 300) * 1000);
    return cachedToken;
}

/**
 * テキストメッセージを送信する
 */
async function sendTextMessage(userId, text) {
    const token = await getAccessToken();
    const botId = process.env.LINE_WORKS_BOT_ID;
    const url = `https://www.worksapis.com/v1.0/bots/${botId}/users/${userId}/messages`;

    await axios.post(url, {
        content: {
            type: "text",
            text: text
        }
    }, {
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        }
    });
}

/**
 * PDFなどのファイルを「Fileメッセージ形式」で直接送信する
 */
async function sendFileMessage(userId, filePath, fileName) {
    try {
        const token = await getAccessToken();
        const botId = process.env.LINE_WORKS_BOT_ID;

        // 1. ファイル名をつけて一度システムへアップロード予約し、uploadUrlとfileIdを取得する
        const reserveUrl = `https://www.worksapis.com/v1.0/bots/${botId}/attachments`;
        console.log("📤 Reserving upload URL...", reserveUrl);
        const stats = fs.statSync(filePath);
        const reserveRes = await axios.post(reserveUrl, {
            fileName: fileName || path.basename(filePath),
            fileSize: stats.size
        }, {
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        const fileId = reserveRes.data.fileId;
        const uploadUrl = reserveRes.data.uploadUrl;
        console.log("✅ Reservation successful. fileId:", fileId, "uploadUrl:", uploadUrl);

        // 2. 取得したuploadUrlに対してファイルをマルチパートでアップロードする
        const form = new FormData();
        form.append('file', fs.createReadStream(filePath));

        console.log("📤 Uploading binary to uploadUrl...");
        await axios.post(uploadUrl, form, {
            headers: {
                ...form.getHeaders(),
                'Authorization': `Bearer ${token}`
            }
        });
        console.log("✅ File binary uploaded successfully.");

        // 2. そのFileIdを使ってユーザーのトークルームに投下する
        const msgUrl = `https://www.worksapis.com/v1.0/bots/${botId}/users/${userId}/messages`;
        console.log("📤 Sending File Message payload...", msgUrl);
        await axios.post(msgUrl, {
            content: {
                type: "file",
                fileId: fileId,
                fileSize: fs.statSync(filePath).size
            }
        }, {
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });
        console.log("✅ File Message sent successfully.");

    } catch (err) {
        console.error("❌ sendFileMessage Failed!");
        if (err.response && err.response.data) {
            console.error("Response Data:", JSON.stringify(err.response.data, null, 2));
        } else {
            console.error(err.message || err);
        }
        throw err;
    }
}

/**
 * ユーザーが送信した画像（アタッチメント）をダウンロードする
 */
async function downloadImage(fileId, destPath) {
    const token = await getAccessToken();
    const botId = process.env.LINE_WORKS_BOT_ID;

    const downloadUrl = `https://www.worksapis.com/v1.0/bots/${botId}/attachments/${fileId}`;

    // 1. redirect先URLを取得する（axiosは自動リダイレクト時にAuthヘッダーを落とすため手動で追従）
    const redirectRes = await axios.get(downloadUrl, {
        headers: { 'Authorization': `Bearer ${token}` },
        maxRedirects: 0,
        validateStatus: status => status >= 200 && status < 400
    });

    let targetUrl = downloadUrl;
    if (redirectRes.status === 302 || redirectRes.status === 301) {
        targetUrl = redirectRes.headers.location;
    }

    // 2. 取得したURLに対して再度Authヘッダ付きでストリームをダウンロードする
    const response = await axios.get(targetUrl, {
        headers: { 'Authorization': `Bearer ${token}` },
        responseType: 'stream'
    });

    const writer = fs.createWriteStream(destPath);
    response.data.pipe(writer);

    return new Promise((resolve, reject) => {
        writer.on('finish', resolve);
        writer.on('error', reject);
    });
}

module.exports = {
    getAccessToken,
    sendTextMessage,
    sendFileMessage,
    downloadImage
};
