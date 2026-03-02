require('dotenv').config();
const { GoogleGenAI } = require('@google/genai');
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

async function test() {
    const userMessage = "たまごっち 6,200円 1個 が抜けてるので追加して！";
    const invoiceData = {
        "items": [
            { "name": "PlayStation5 Pro", "unit": 109400, "qty": 3, "total": 328200 }
        ],
        "raw_text": "PlayStation5 Pro 328,200円\nたまごっち 6,200円"
    };

    const rawTextContext = invoiceData.raw_text ? `\n【レシートの元の読み取りテキスト（参考）】\n${invoiceData.raw_text}\n` : '';
    const prompt = `あなたは請求書の項目の修正アシスタントです。
以下の現在のJSONデータに対して、ユーザーの指示通りの修正を行ってください。
修正後の結果は、元のJSONと全く同じスキーマ（必ず { "items": [ ... ] } の形式）のJSONのみを出力してください。Markdownのバッククォートなどは付けないこと。
${rawTextContext}
【現在のJSON】
${JSON.stringify(invoiceData.items)}

【ユーザーの指示】
${userMessage}`;

    try {
        console.log("PROMPT:\n" + prompt);
        const response = await ai.models.generateContent({
            model: 'gemini-2.5-flash-lite',
            contents: prompt,
            config: { temperature: 0.1 }
        });

        console.log("RESPONSE:\n" + response.text);

        let newJsonStr = response.text.replace(/\`\`\`json/g, '').replace(/\`\`\`/g, '').trim();
        let newData;
        try {
            newData = JSON.parse(newJsonStr);
            if (Array.isArray(newData)) {
                newData = { items: newData };
            } else if (!newData.items) {
                newData = { items: [] };
            }
        } catch (err) {
            console.error("JSON PARSE ERROR!");
            throw new Error("JSON Parse Error");
        }
        console.log("FINAL DATA:", newData);
    } catch (e) {
        console.error("API Error:", e);
    }
}
test();
