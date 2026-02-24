const lineWorksApi = require('./lineWorksApi');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

async function testUploadCurl() {
    try {
        const dummyPath = path.join(__dirname, 'test_dummy.pdf');
        fs.writeFileSync(dummyPath, '%PDF-1.4\n%Dummy PDF content for testing');

        const token = await lineWorksApi.getAccessToken();
        const botId = process.env.LINE_WORKS_BOT_ID;
        const uploadUrl = `https://www.worksapis.com/v1.0/bots/${botId}/attachments`;

        console.log("Starting upload test via CURL...");

        const curlCmd = `curl -X POST "${uploadUrl}" -H "Authorization: Bearer ${token}" -F "fileName=test_dummy.pdf" -F "file=@${dummyPath}"`;

        const output = execSync(curlCmd, { encoding: 'utf-8' });
        console.log("CURL output:", output);

        fs.unlinkSync(dummyPath);
    } catch (e) {
        console.error("Test failed!", e.stderr || e.message);
    }
}

testUploadCurl();
