const lineWorksApi = require('./lineWorksApi');

async function testAuth() {
    try {
        console.log("Checking LINE WORKS API authentication...");
        const token = await lineWorksApi.getAccessToken();
        console.log("✅ Successfully generated JWT Token:", token.substring(0, 15) + "...");
        console.log("\nIf this worked, the keys provided by the user are correct.");
        console.log("The issue must be either:");
        console.log("1. The Bot's 'Message Event' toggle is off in the Developer Console");
        console.log("2. The User is sending the message to a 1:1 chat before the Bot was fully indexed");
    } catch (e) {
        console.error("❌ Authentication failed!");
        if (e.response && e.response.data) {
            console.error(e.response.data);
        } else {
            console.error(e.message || e);
        }
    }
}

testAuth();
