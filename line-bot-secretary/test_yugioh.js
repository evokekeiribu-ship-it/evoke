require('dotenv').config();
const { GoogleGenAI } = require('@google/genai');
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

async function test() {
    const userMessage = "遊戯王を追加して";
    const invoiceData = {
        "items": [
            { "name": "Nintendo Switch (有機ELモデル) ホワイト", "unit": 41500, "qty": 1, "total": 41500 },
            { "name": "Nintendo Switch Lite コーラル", "unit": 22650, "qty": 2, "total": 45300 }
        ],
        "raw_text": "Nintendo Switch (有機ELモデル) ホワイト 41,500円\nNintendo Switch Lite コーラル 22,650円\n"
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

    for (let i = 0; i < 5; i++) {
        try {
            const response = await ai.models.generateContent({
                model: 'gemini-2.5-flash-lite',
                contents: prompt,
                config: { temperature: 0.1 }
            });

            let newJsonStr = response.text.replace(/\`\`\`json/g, '').replace(/\`\`\`/g, '').trim();
            try {
                JSON.parse(newJsonStr);
                console.log(`Test ${i}: SUCCESS`);
            } catch (err) {
                console.error(`Test ${i}: PARSE ERROR\nRaw Output:\n${response.text}`);
            }
        } catch (e) {
            console.error(`Test ${i}: API Error:`, e.message);
        }
    }
}
test();
