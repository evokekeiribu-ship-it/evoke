const lineWorksApi = require('./lineWorksApi');
const fs = require('fs');
const path = require('path');

async function testUpload() {
    try {
        const dummyPath = path.join(__dirname, 'test_dummy.pdf');
        fs.writeFileSync(dummyPath, '%PDF-1.4\n%Dummy PDF content for testing');

        // Use the ID you saw in the logs for testing
        const userId = '90a0c666-dbc7-4848-19dc-04106d1fc8ed';

        console.log("Starting upload test for userId:", userId);
        await lineWorksApi.sendFileMessage(userId, dummyPath, 'test_dummy.pdf');

        fs.unlinkSync(dummyPath);
        console.log("Test finished successfully!");
    } catch (e) {
        console.error("Test failed!");
    }
}

testUpload();
