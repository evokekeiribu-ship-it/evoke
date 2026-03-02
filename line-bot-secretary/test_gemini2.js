require('dotenv').config();
const { GoogleGenAI } = require('@google/genai');
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

async function test() {
    const invoiceData = {
        "items": [
            { "name": "PlayStation5 Pro", "unit": 109400, "qty": 3, "total": 328200 }
        ]
    };
    const userMessage = "たまごっち 6,200円 1個 が抜けてるので追加して！";

    const prompt = `あなたは請求書の項目の修正アシスタントです。
以下の現在のJSONデータに対して、ユーザーの指示通りの修正を行ってください。
修正後の結果は、元のJSONと全く同じスキーマのJSONのみを出力してください（Markdownのバッククォートなどは付けないこと）。

【現在のJSON】
${JSON.stringify(invoiceData)}

【ユーザーの指示】
${userMessage}`;

    try {
        const response = await ai.models.generateContent({
            model: 'gemini-2.5-flash-lite',
            contents: prompt,
            config: { temperature: 0.1 }
        });
        console.log("Response text:", response.text);

        let newJsonStr = response.text.replace(/\`\`\`json/g, '').replace(/\`\`\`/g, '').trim();
        console.log("JSON string to parse:", newJsonStr);
        let newData = JSON.parse(newJsonStr);
        console.log("Parsed Data:", newData);
    } catch (e) {
        console.error("Error:", e);
    }
}
test();
