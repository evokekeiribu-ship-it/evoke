const lineWorksApi = require('./lineWorksApi');
const axios = require('axios');
const fs = require('fs');

async function testDownload() {
    try {
        const token = await lineWorksApi.getAccessToken();
        const fileId = "jp1.1771845260687153112.1771931660.2.11709793.401110272.412033431.37";
        const botId = process.env.LINE_WORKS_BOT_ID;
        const downloadUrl = `https://www.worksapis.com/v1.0/bots/${botId}/attachments/${fileId}`;

        // Step 1: Get redirect URL
        const response1 = await axios.get(downloadUrl, {
            headers: { 'Authorization': `Bearer ${token}` },
            maxRedirects: 0,
            validateStatus: status => status >= 200 && status < 400
        });

        const redirectUrl = response1.headers.location;
        console.log("Redirect URL:", redirectUrl);

        // Step 2: Download from redirect URL WITH Auth header
        const response2 = await axios.get(redirectUrl, {
            headers: { 'Authorization': `Bearer ${token}` },
            responseType: 'stream'
        });

        const writer = fs.createWriteStream('./test_image.jpg');
        response2.data.pipe(writer);

        writer.on('finish', () => console.log("Download complete!"));
        writer.on('error', (err) => console.error("Writer error", err));

    } catch (e) {
        console.error("Test failed!", e.response ? e.response.status : e.message);
    }
}

testDownload();
