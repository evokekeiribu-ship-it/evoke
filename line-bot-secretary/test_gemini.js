require('dotenv').config();
const { GoogleGenAI } = require('@google/genai');
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

async function test() {
    try {
        const response = await ai.models.generateContent({
            model: 'gemini-2.5-flash-lite',
            contents: 'test',
            config: { temperature: 0.1 }
        });
        console.log("Response text:", response.text);
    } catch (e) {
        console.error("Error:", e);
    }
}
test();
