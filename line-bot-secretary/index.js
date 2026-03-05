require('dotenv').config();
const express = require('express');
const { GoogleGenAI } = require('@google/genai');
const fs = require('fs');
const path = require('path');
const { spawn, exec, execFile } = require('child_process');
const https = require('https');

// LINE WORKS API 用の独自モジュール
const lineWorksApi = require('./lineWorksApi');

// Google API 認証情報の環境変数からの復元 (Render対応)
if (process.env.GOOGLE_CREDENTIALS_JSON) {
    try {
        const credsFile = path.join(__dirname, 'google-credentials.json');
        fs.writeFileSync(credsFile, process.env.GOOGLE_CREDENTIALS_JSON);
        process.env.GOOGLE_APPLICATION_CREDENTIALS = credsFile;
        console.log("✅ Google Credentials JSON file created from environment variable.");
    } catch (err) {
        console.error("❌ Error creating Google Credentials file:", err);
    }
}

// 2. クライアントの準備
const app = express();
app.use(express.json()); // LINE WORKS からの JSON ボディをパースする

const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

// ユーザーごとの会話セッションを保存するオブジェクト
const userChats = {};
// ピック依頼用の状態管理オブジェクト
const userStates = {};

// 画像の一時保存用ディレクトリ
const rootDir = path.dirname(__dirname); // __dirname is line-bot-secretary, rootDir is deveropment
const invoiceInDir = path.join(rootDir, '請求書作成', '請求書作成依頼');
const invoiceOutDir = path.join(rootDir, '請求書作成', '作成済み請求書');

// 3. Webhookエンドポイント（LINE WORKSからのメッセージを受け取る場所）
app.post('/webhook', async (req, res) => {
    // 常に200 OKを素早く返す
    res.status(200).send('OK');

    try {
        const event = req.body;
        console.log("=== Webhook到達 ===");
        console.log(JSON.stringify(event, null, 2));

        if (event && event.type === 'message') {
            await handleEvent(event);
        }
    } catch (err) {
        console.error("Webhook処理エラー:", err);
    }
});

// （念のためダウンロード用エンドポイントも残しておきます）
app.get('/download/:dateFolder/:filename', (req, res) => {
    const dateFolder = req.params.dateFolder;
    const filename = req.params.filename;

    if (dateFolder.includes('..') || filename.includes('..')) {
        return res.status(403).send('Forbidden');
    }

    const filePath = path.join(invoiceOutDir, dateFolder, filename);

    if (fs.existsSync(filePath)) {
        res.download(filePath, filename);
    } else {
        res.status(404).send('ファイルが見つかりません');
    }
});

app.get('/download-order/:filename', (req, res) => {
    const filename = req.params.filename;

    if (filename.includes('..')) {
        return res.status(403).send('Forbidden');
    }

    const manualOutDir = path.join(rootDir, '注文確認');
    const filePath = path.join(manualOutDir, filename);

    if (fs.existsSync(filePath)) {
        res.download(filePath, filename);
    } else {
        res.status(404).send('ファイルが見つかりません');
    }
});

// ============================
// Gemini Vision APIで画像OCR
// ============================
async function parseImageWithGemini(imagePath) {
    const imageData = fs.readFileSync(imagePath);
    const base64Image = imageData.toString('base64');
    const ext = path.extname(imagePath).toLowerCase();
    const mimeType = ext === '.png' ? 'image/png' : 'image/jpeg';

    const today = new Date();
    const todayStr = today.toISOString().split('T')[0];
    const deadlineDate = new Date(today);
    deadlineDate.setDate(deadlineDate.getDate() + 7);
    const deadlineStr = deadlineDate.toISOString().split('T')[0];

    const prompt = `この画像は商品の仕入れリスト・発注書・納品書・レシートです。
まず画像の商品テーブルに何行あるか数えてください。
次に、その全ての行を漏れなく読み取り、以下のJSONフォーマットのみを返してください。

{
  "today": "${todayStr}",
  "deadline": "${deadlineStr}",
  "items": [
    {
      "name": "商品名（画像の通り正確に記載。略さない）",
      "unit": 単価（画像に記載された金額そのまま、整数のみ）,
      "qty": 数量（整数のみ）,
      "total": 合計（単価×数量、整数のみ）
    }
  ]
}

厳守事項：
- テーブルの全行を必ず読み取ること（1行も飛ばさない）
- Switch Sports、ジョイコン、ゼルダ、NS2、メガシンフォニアなど略称の商品も全て含める
- 商品名は画像の記載通りに正確に書く（省略・変換しない）
- 金額は画像に書いてある数値をそのまま使う（計算しない）
- JSONのみ出力（マークダウン記法・コードブロック不要）
- items配列を途中で切らない（全商品を含めること）`;

    const response = await ai.models.generateContent({
        model: 'gemini-2.5-flash',
        contents: [
            {
                parts: [
                    { text: prompt },
                    {
                        inlineData: {
                            mimeType: mimeType,
                            data: base64Image
                        }
                    }
                ]
            }
        ],
        config: {
            temperature: 0.1
        }
    });

    let jsonStr = response.text;
    const jsonMatch = jsonStr.match(/\{[\s\S]*\}/);
    if (jsonMatch) jsonStr = jsonMatch[0];

    const parsed = JSON.parse(jsonStr);
    return parsed;
}

// 4. メッセージ受信時の処理
async function handleEvent(event) {
    if (!event.content || !event.source) {
        return Promise.resolve(null);
    }

    // LINE WORKSでは送信者のIDは `accountId` （または `userId`）に入ります
    const userId = event.source.accountId || event.source.userId;

    // --- 画像メッセージ（請求書作成）の処理 ---
    if (event.content.type === 'image') {
        return new Promise(async (resolve) => {
            console.log("👉 LINE WORKSから画像を受信しました！請求書作成を開始します。");

            // 処理中に移行
            userStates[userId] = { state: 'processing' };

            await lineWorksApi.sendTextMessage(userId, "【システム】レシート画像を認識しました！請求書を作成しています...⏳").catch(e => console.error(e));

            try {
                // 1. 請求書作成依頼フォルダ内を空にする（古い画像を消す）
                if (!fs.existsSync(invoiceInDir)) {
                    fs.mkdirSync(invoiceInDir, { recursive: true });
                }
                const oldFiles = fs.readdirSync(invoiceInDir);
                for (const file of oldFiles) {
                    fs.unlinkSync(path.join(invoiceInDir, file));
                }

                // 2. LINE WORKSから画像をダウンロードして保存
                const fileId = event.content.fileId;
                const imagePath = path.join(invoiceInDir, `${fileId}.jpg`);
                await lineWorksApi.downloadImage(fileId, imagePath);

                console.log("画像の保存が完了しました。Gemini Vision APIでOCRを実行します。");

                // 3. Gemini Vision APIでOCR（B案）
                let parsedData = null;
                try {
                    parsedData = await parseImageWithGemini(imagePath);
                } catch (geminiErr) {
                    console.error(`Gemini OCRエラー: ${geminiErr.message}`);
                    await lineWorksApi.sendTextMessage(userId, `【エラー】画像の読み取りに失敗しました💦\n${geminiErr.message}`).catch(e => console.error(e));
                    delete userStates[userId];
                    return resolve(null);
                }

                if (!parsedData || !parsedData.items || parsedData.items.length === 0) {
                    await lineWorksApi.sendTextMessage(userId, "【システム】レシートから商品を読み取れませんでした💦\n明るい場所で撮り直すか、「請求書」と送信して手動作成をお試しください。").catch(e => console.error(e));
                    delete userStates[userId];
                    return resolve(null);
                }

                // 単価調整ルール: 20000円以上 → -100円、20000円未満 → -20円
                parsedData.items = parsedData.items.map(it => {
                    const adjustment = it.unit >= 20000 ? -100 : -20;
                    const adjustedUnit = it.unit + adjustment;
                    return {
                        ...it,
                        unit: adjustedUnit,
                        total: adjustedUnit * it.qty
                    };
                });

                // 4. 確認メッセージの生成
                let confirmText = "【システム】画像から以下の内容を読み取りました👀\n\n【商品リスト】\n";
                let total = 0;
                parsedData.items.forEach(it => {
                    confirmText += `- ${it.name} ${it.qty}個 (¥${it.total.toLocaleString()})\n`;
                    total += it.total;
                });

                confirmText += `\n合計金額: ¥${total.toLocaleString()}\n\nこの内容で請求書を作成してもよろしいですか？👇\n1: はい\n2: キャンセル\n\n【修正がある場合】\n「たまごっち 6,200円 1個 が抜けてるよ！」のようにメッセージを送ってください。`;

                await lineWorksApi.sendTextMessage(userId, confirmText).catch(e => console.error(e));

                // 5. 状態の更新
                userStates[userId] = {
                    state: 'awaiting_ocr_confirm',
                    invoiceData: parsedData,
                    fileId: fileId
                };

                resolve(null);

            } catch (err) {
                console.error("画像処理エラー:", err);
                await lineWorksApi.sendTextMessage(userId, "【エラー】処理中に予期せぬエラーが発生しました💦").catch(e => console.error(e));
                delete userStates[userId];
                resolve(null);
            }
        });
    }

    // テキスト以外のメッセージは無視する
    if (event.content.type !== 'text') {
        return Promise.resolve(null);
    }

    const userMessage = event.content.text;

    // 処理中のメッセージは無視
    if (userStates[userId] && userStates[userId].state && userStates[userId].state.startsWith('processing')) {
        return Promise.resolve(null);
    }

    // --- キャンセル処理 ---
    if (userMessage === "キャンセル") {
        if (userStates[userId]) {
            delete userStates[userId];
            return lineWorksApi.sendTextMessage(userId, "【システム】処理をキャンセルしました。最初からやり直してください😊");
        }
    }

    // --- 戻る処理 ---
    if (userMessage === "戻る" || userMessage === "もどる") {
        if (userStates[userId]) {
            const currentState = userStates[userId].state;

            // 請求書作成フローの巻き戻し
            if (currentState === 'awaiting_manual_tax') {
                userStates[userId].state = 'awaiting_manual_qty';
                return lineWorksApi.sendTextMessage(userId, "【システム】1つ前の項目に戻ります。\n個数を半角数字で教えてください");
            } else if (currentState === 'awaiting_manual_qty') {
                userStates[userId].state = 'awaiting_manual_price';
                return lineWorksApi.sendTextMessage(userId, "【システム】1つ前の項目に戻ります。\n金額（単価）を半角数字で教えてください");
            } else if (currentState === 'awaiting_manual_price') {
                userStates[userId].state = 'awaiting_manual_content';
                return lineWorksApi.sendTextMessage(userId, "【システム】1つ前の項目に戻ります。\n内容を教えてください");
            } else if (currentState === 'awaiting_manual_content') {
                userStates[userId].state = 'awaiting_manual_dest';
                return lineWorksApi.sendTextMessage(userId, "【システム】1つ前の項目に戻ります。\n宛先を教えてください");
            } else if (currentState === 'awaiting_manual_dest') {
                return lineWorksApi.sendTextMessage(userId, "【システム】これ以上戻れません。\nやめる場合は「キャンセル」と入力してください");
            }

            // ピック依頼フローの巻き戻し
            if (currentState === 'awaiting_qty') {
                userStates[userId].state = 'awaiting_dest';
                return lineWorksApi.sendTextMessage(userId, "【システム】1つ前の項目に戻ります。\n宛先を選択してください👇\n1: ミナミトランスポートレーション\n2: TUYOSHI\n(半角の 1 か 2 を送信してください)");
            } else if (currentState === 'awaiting_dest') {
                return lineWorksApi.sendTextMessage(userId, "【システム】これ以上戻れません。\nやめる場合は「キャンセル」と入力してください");
            }
        }
    }

    // 状態に基づいたフロー処理
    if (userStates[userId] && userStates[userId].state === 'awaiting_image_delete') {
        const isYes = userMessage === '1' || userMessage === 'はい' || userMessage === 'ハイ' || userMessage.toLowerCase() === 'yes';
        const isNo = userMessage === '2' || userMessage === 'いいえ' || userMessage === 'イイエ' || userMessage.toLowerCase() === 'no';

        if (isYes) {
            delete userStates[userId];
            try {
                if (fs.existsSync(invoiceInDir)) {
                    const oldFiles = fs.readdirSync(invoiceInDir);
                    for (const file of oldFiles) {
                        fs.unlinkSync(path.join(invoiceInDir, file));
                    }
                }
                return lineWorksApi.sendTextMessage(userId, "【システム】元画像を削除しました！🗑️");
            } catch (err) {
                console.error("画像削除エラー:", err);
                return lineWorksApi.sendTextMessage(userId, "【システム】画像の削除中にエラーが発生しました💦");
            }
        } else if (isNo) {
            delete userStates[userId];
            return lineWorksApi.sendTextMessage(userId, "【システム】元画像を保持します。📂");
        } else {
            // 1,2 以外の関連しないメッセージが来た場合は状態をクリアして、下のGeminiに流す
            console.log("DEBUG: fallthrough for unrecognized message in delete prompt:", userMessage);
            delete userStates[userId];
        }

    } else if (userStates[userId] && userStates[userId].state === 'awaiting_ocr_confirm') {
        const isYes = userMessage === 'はい' || userMessage === 'ハイ' || userMessage.toLowerCase() === 'yes' || userMessage === '1';
        const isNo = userMessage === 'キャンセル' || userMessage === 'いいえ' || userMessage === 'イイエ' || userMessage.toLowerCase() === 'no' || userMessage === '2';

        if (isYes) {
            const invoiceData = userStates[userId].invoiceData;
            userStates[userId].state = 'processing';

            return new Promise(async (resolve) => {
                await lineWorksApi.sendTextMessage(userId, "【システム】承知しました！PDFを作成しています...⏳").catch(e => console.error(e));

                const scriptPath = path.join(rootDir, '請求書作成', 'App_Core', 'batch_gen.py');
                const workDir = path.dirname(scriptPath);
                const pythonExe = process.env.PYTHON_CMD || 'python';
                const execOptions = { cwd: workDir, env: { ...process.env } };

                execFile(pythonExe, [scriptPath, '--generate-from-json', JSON.stringify(invoiceData)], execOptions, async (error, stdout, stderr) => {
                    if (error) {
                        console.error(`実行エラー: ${error.message}\n${stderr}`);
                        let errDetails = stderr ? stderr.substring(0, 500) : error.message.substring(0, 500);
                        await lineWorksApi.sendTextMessage(userId, `【システムエラー詳細】\nPDF生成に失敗しました。\n\n詳細:\n${errDetails}\n\nこの画面をスクショして開発者に送付してください💦`).catch(e => console.error(e));
                        delete userStates[userId];
                        return resolve(null);
                    }

                    // PDFパスの抽出
                    let pdfPathMatch = stdout.match(/___PDF_GENERATED___:(.+)/);
                    if (!pdfPathMatch || !pdfPathMatch[1]) {
                        await lineWorksApi.sendTextMessage(userId, "【システム】PDFが見つかりませんでした💦").catch(e => console.error(e));
                        delete userStates[userId];
                        return resolve(null);
                    }

                    const latestPdfPath = pdfPathMatch[1].trim();
                    const foundFilename = path.basename(latestPdfPath);

                    await lineWorksApi.sendTextMessage(userId, "【システム】請求書が完成しました！✨\nPDFファイルを送信します...").catch(e => console.error(e));
                    await lineWorksApi.sendFileMessage(userId, latestPdfPath, foundFilename).catch(err => console.error("Push Error :", err));

                    await lineWorksApi.sendTextMessage(userId, "【システム】元画像を直ちに削除しますか？👇\n1: はい\n2: いいえ\n(関係ないメッセージを送ると状態が解除されAIと会話できます)").catch(err => console.error(err));
                    userStates[userId] = { state: 'awaiting_image_delete' };

                    resolve(null);
                });
            });
        } else if (isNo) {
            delete userStates[userId];
            return lineWorksApi.sendTextMessage(userId, "【システム】作成をキャンセルしました。手動で作成する場合は「請求書」と送信してください。");
        } else {
            return new Promise(async (resolve) => {
                await lineWorksApi.sendTextMessage(userId, "【システム】AIが内容を修正しています... 少々お待ちください🤖").catch(e => console.error(e));
                try {
                    const rawTextContext = userStates[userId].invoiceData.raw_text ? `\n【レシートの元の読み取りテキスト（参考）】\n${userStates[userId].invoiceData.raw_text}\n` : '';
                    const prompt = `あなたは請求書の項目の修正アシスタントです。
以下の現在のJSONデータに対して、ユーザーの指示通りの修正を行ってください。
修正後の結果は、元のJSONと全く同じスキーマ（必ず { "items": [ ... ] } の形式）のJSONのみを出力してください。Markdownのバッククォートなどは付けないこと。
${rawTextContext}
【現在のJSON】
${JSON.stringify(userStates[userId].invoiceData.items)}

【ユーザーの指示】
${userMessage}`;

                    const response = await ai.models.generateContent({
                        model: 'gemini-2.5-flash-lite',
                        contents: prompt,
                        config: {
                            temperature: 0.1,
                            responseMimeType: "application/json"
                        }
                    });

                    let newJsonStr = response.text;
                    const jsonMatch = newJsonStr.match(/\{[\s\S]*\}/);
                    if (jsonMatch) {
                        newJsonStr = jsonMatch[0];
                    }

                    let newData;
                    try {
                        newData = JSON.parse(newJsonStr);
                        if (Array.isArray(newData)) {
                            newData = { items: newData };
                        } else if (!newData.items) {
                            newData = { items: [] };
                        }
                    } catch (err) {
                        throw new Error("JSON Parse Error");
                    }

                    userStates[userId].invoiceData.items = newData.items;

                    let confirmText = "【システム】修正が完了しました！以下の内容でよろしいですか？👀\n\n【商品リスト】\n";
                    let total = 0;
                    newData.items.forEach(it => {
                        confirmText += `- ${it.name} ${it.qty}個 (¥${it.total.toLocaleString()})\n`;
                        total += it.total;
                    });
                    confirmText += `\n合計金額: ¥${total.toLocaleString()}\n\nこの内容で作成してもよろしいですか？👇\n1: はい\n2: キャンセル\n\n【さらに修正がある場合】\nもう一度指示を送信してください。`;

                    await lineWorksApi.sendTextMessage(userId, confirmText).catch(e => console.error(e));
                    resolve(null);
                } catch (e) {
                    console.error("Gemini correction error:", e);
                    const errMsg = e.message || String(e);
                    await lineWorksApi.sendTextMessage(userId, `【エラー】AIによる修正に失敗しました💦\n原因: ${errMsg}\n\n「2」で一度キャンセルしてください。`).catch(e => console.error(e));
                    resolve(null);
                }
            });
        }

    } else if (userStates[userId] && userStates[userId].state === 'awaiting_dest') {
        if (['1', '2', '3', '4'].includes(userMessage)) {
            userStates[userId].state = 'awaiting_qty';
            userStates[userId].destChoice = userMessage;
            return lineWorksApi.sendTextMessage(userId, "【システム】ピック依頼の個数を教えてください！（半角数字のみ）");
        } else {
            return lineWorksApi.sendTextMessage(userId, "【システム】エラー: 1 から 4 のいずれかを入力してください。\n（やめる場合は「キャンセル」と入力）");
        }

    } else if (userStates[userId] && userStates[userId].state === 'awaiting_qty') {
        const qty = parseInt(userMessage, 10);
        if (!isNaN(qty) && qty > 0) {
            const destChoice = userStates[userId].destChoice;
            userStates[userId].state = 'processing';

            return new Promise(async (resolve) => {
                await lineWorksApi.sendTextMessage(userId, "【システム】個数を承知しました！請求書を作成しています...⏳").catch(e => console.error(e));

                const scriptPath = path.join(rootDir, '請求書作成', 'App_Core', 'pick_invoice.py');
                const workDir = path.dirname(scriptPath);
                const pythonExe = process.env.PYTHON_CMD || 'python';

                exec(`"${pythonExe}" "${scriptPath}" ${destChoice} ${qty}`, { cwd: workDir }, async (error, stdout, stderr) => {
                    if (error) {
                        console.error(`実行エラー: ${error}`);
                        await lineWorksApi.sendTextMessage(userId, `【エラー】ピック用請求書の作成に失敗しました💦\n${error.message}`).catch(e => console.error(e));
                        delete userStates[userId];
                        return resolve(null);
                    }

                    // 最新のピック依頼用PDFを探す
                    let latestPdfPath = null;
                    let latestTime = 0;
                    let foundFilename = null;

                    if (fs.existsSync(invoiceOutDir)) {
                        const dateFolders = fs.readdirSync(invoiceOutDir);
                        for (const dFolder of dateFolders) {
                            const folderPath = path.join(invoiceOutDir, dFolder);
                            if (fs.statSync(folderPath).isDirectory()) {
                                const files = fs.readdirSync(folderPath);
                                for (const file of files) {
                                    if (file.includes('-P') && file.endsWith('.pdf')) {
                                        const filePath = path.join(folderPath, file);
                                        const stat = fs.statSync(filePath);
                                        if (stat.mtimeMs > latestTime) {
                                            latestTime = stat.mtimeMs;
                                            latestPdfPath = filePath;
                                            foundFilename = file;
                                        }
                                    }
                                }
                            }
                        }
                    }

                    if (!latestPdfPath) {
                        await lineWorksApi.sendTextMessage(userId, "【システム】スクリプトは成功しましたが、ピック用のPDFが見つかりませんでした💦").catch(e => console.error(e));
                        delete userStates[userId];
                        return resolve(null);
                    }

                    let destName = 'その他';
                    if (destChoice === '1') destName = 'ミナミトランスポートレーション';
                    else if (destChoice === '2') destName = 'TUYOSHI';
                    else if (destChoice === '3') destName = '株式会社りんご';
                    else if (destChoice === '4') destName = '寺本康太';

                    await lineWorksApi.sendTextMessage(userId, `【システム】${destName}宛 (${qty}個) の請求書が完成しました！✨\nPDFファイルを送信します...`).catch(e => console.error(e));
                    await lineWorksApi.sendFileMessage(userId, latestPdfPath, foundFilename).catch(err => console.error("Push Error (PDF送信):", err.message || err));

                    // ※LINE WORKS のローディングスピナー対策：ファイル送信直後に明示的にテキストメッセージを添える
                    await lineWorksApi.sendTextMessage(userId, "【システム】ピック依頼の作成が完了しました！🧾").catch(e => console.error(e));

                    delete userStates[userId];
                    resolve(null);
                });
            });
        } else {
            return lineWorksApi.sendTextMessage(userId, "【システム】エラー: 有効な数字（1以上の整数）を入力してください。\n（やめる場合は「キャンセル」と入力）");
        }

    } else if (userStates[userId] && userStates[userId].state === 'awaiting_manual_dest') {
        userStates[userId].manualDest = userMessage;
        userStates[userId].state = 'awaiting_manual_content';
        return lineWorksApi.sendTextMessage(userId, "【システム】内容を教えてください");

    } else if (userStates[userId] && userStates[userId].state === 'awaiting_manual_content') {
        userStates[userId].manualContent = userMessage;
        userStates[userId].state = 'awaiting_manual_price';
        return lineWorksApi.sendTextMessage(userId, "【システム】金額（単価）を半角数字で教えてください");

    } else if (userStates[userId] && userStates[userId].state === 'awaiting_manual_price') {
        const price = parseInt(userMessage, 10);
        if (!isNaN(price) && price >= 0) {
            userStates[userId].manualPrice = price;
            userStates[userId].state = 'awaiting_manual_qty';
            return lineWorksApi.sendTextMessage(userId, "【システム】個数を半角数字で教えてください");
        } else {
            return lineWorksApi.sendTextMessage(userId, "【システム】エラー: 有効な数字を入力してください。");
        }

    } else if (userStates[userId] && userStates[userId].state === 'awaiting_manual_qty') {
        const mqts = parseInt(userMessage, 10);
        if (!isNaN(mqts) && mqts > 0) {
            userStates[userId].manualQty = mqts;
            userStates[userId].state = 'awaiting_manual_tax';
            return lineWorksApi.sendTextMessage(userId, "【システム】税込みですか？税抜きですか？\n(1: 税込み / 2: 税抜き)\n(半角の 1 か 2 を送信してください)");
        } else {
            return lineWorksApi.sendTextMessage(userId, "【システム】エラー: 有効な数字（1以上）を入力してください。");
        }

    } else if (userStates[userId] && userStates[userId].state === 'awaiting_manual_tax') {
        if (userMessage === '1' || userMessage === '2') {
            const taxType = userMessage;

            const dest = userStates[userId].manualDest;
            const content = userStates[userId].manualContent;
            const price = userStates[userId].manualPrice;
            const qty = userStates[userId].manualQty;

            userStates[userId].state = 'processing';

            return new Promise(async (resolve) => {
                await lineWorksApi.sendTextMessage(userId, "【システム】承知しました！請求書を作成しています...⏳").catch(e => console.error(e));

                const scriptPath = path.join(rootDir, '請求書作成', 'App_Core', 'manual_invoice.py');
                const workDir = path.dirname(scriptPath);
                const pythonExe = process.env.PYTHON_CMD || 'python';

                const cmdArgs = `"${dest}" "${content}" "${price}" "${qty}" "${taxType}"`;

                // 環境変数を明示的に渡す (Render対応)
                const execOptions = {
                    cwd: workDir,
                    env: { ...process.env }
                };

                exec(`"${pythonExe}" "${scriptPath}" ${cmdArgs}`, execOptions, async (error, stdout, stderr) => {
                    if (error) {
                        console.error(`カスタム請求書実行エラー: ${error}`);
                        await lineWorksApi.sendTextMessage(userId, `【エラー】カスタム請求書の作成に失敗しました💦\n${error.message}`).catch(e => console.error(e));
                        delete userStates[userId];
                        return resolve(null);
                    }

                    // 作成済み請求書を探索
                    let latestPdfPath = null;
                    let latestTime = 0;
                    let foundFilename = null;

                    if (fs.existsSync(invoiceOutDir)) {
                        const dateFolders = fs.readdirSync(invoiceOutDir);
                        for (const dFolder of dateFolders) {
                            const folderPath = path.join(invoiceOutDir, dFolder);
                            if (fs.statSync(folderPath).isDirectory()) {
                                const files = fs.readdirSync(folderPath);
                                for (const file of files) {
                                    if (file.endsWith('.pdf')) {
                                        const filePath = path.join(folderPath, file);
                                        const stat = fs.statSync(filePath);
                                        if (stat.mtimeMs > latestTime) {
                                            latestTime = stat.mtimeMs;
                                            latestPdfPath = filePath;
                                            foundFilename = file;
                                        }
                                    }
                                }
                            }
                        }
                    }

                    if (!latestPdfPath) {
                        await lineWorksApi.sendTextMessage(userId, "【システム】スクリプトは成功しましたが、PDFが見つかりませんでした💦").catch(e => console.error(e));
                        delete userStates[userId];
                        return resolve(null);
                    }

                    await lineWorksApi.sendTextMessage(userId, `【システム】${dest}御中 の請求書（注文確認）が完成しました！✨\nPDFファイルを送信します...`).catch(e => console.error(e));
                    await lineWorksApi.sendFileMessage(userId, latestPdfPath, foundFilename).catch(err => console.error("Push Error (PDF送信):", err.message || err));

                    delete userStates[userId];
                    resolve(null);
                });
            });
        } else {
            return lineWorksApi.sendTextMessage(userId, "【システム】エラー: 1 または 2 を入力してください。\n（やめる場合は「キャンセル」と入力）");
        }
    }

    // --- 請求書作成（開始トリガー）の処理 ---
    if (userMessage === "請求書作成") {
        userStates[userId] = { state: 'awaiting_manual_dest' };
        return lineWorksApi.sendTextMessage(userId, "【システム】指定請求書の作成を開始します！\n宛先を教えてください");
    }

    // --- ピック依頼（開始トリガー）の処理 ---
    if (userMessage === "ピック依頼") {
        userStates[userId] = { state: 'awaiting_dest' };
        return lineWorksApi.sendTextMessage(userId, "【システム】ピック依頼の請求書を作成します！\n宛先を選択してください：\n\n1: 株式会社ミナミトランスポートレーション\n2: 株式会社TUYOSHI\n3: 株式会社りんご\n4: 寺本康太\n\n（半角数字で「1」から「4」のいずれかを送信してください）");
    }

    // --- レシート画像読み取り（開始トリガー）の処理 ---
    if (userMessage === "レシート読取" || userMessage === "レシート読み取り") {
        userStates[userId] = { state: 'awaiting_receipt_image' };
        return lineWorksApi.sendTextMessage(userId, "【システム】レシート画像から請求書を自動作成します！\n画像を送信してください📸");
    }

    // --- PC遠隔操作コマンドの処理 ---
    if (userMessage === 'コマンド:メモ帳') {
        return new Promise(async (resolve) => {
            console.log("👉 LINE WORKSから遠隔操作コマンド「メモ帳起動」を受信しました！");
            exec('notepad.exe', async (error, stdout, stderr) => {
                let replyText = "【システム】PC側でメモ帳を起動しました！💻✨";
                if (error) {
                    console.error(`実行エラー: ${error}`);
                    replyText = `【エラー】メモ帳の起動に失敗しました💦\n${error.message}`;
                }
                await lineWorksApi.sendTextMessage(userId, replyText).catch(e => console.error(e));
                resolve(null);
            });
        });
    }

    if (userMessage === 'コマンド:注文確認') {
        return new Promise(async (resolve) => {
            console.log("👉 LINE WORKSから遠隔操作コマンド「注文確認」を受信しました！");
            await lineWorksApi.sendTextMessage(userId, "【システム】注文確認スクリプトの実行を開始します... 少々お待ちください⏳").catch(e => console.error(e));

            const scriptPath = path.join(rootDir, '注文確認', 'check_apple_orders.py');
            const workDir = path.dirname(scriptPath);
            const pythonExe = process.env.PYTHON_CMD || 'python';

            // 環境変数を明示的に渡す (Render対応)
            const execOptions = {
                cwd: workDir,
                env: { ...process.env }
            };

            exec(`"${pythonExe}" "${scriptPath}"`, execOptions, async (error, stdout, stderr) => {
                let resultText = "【システム】スクリプトの実行が完了しました！✨\n（変更があれば別途通知されます）";
                if (error) {
                    console.error(`実行エラー: ${error}`);
                    resultText = `【エラー】実行に失敗しました💦\n${error.message}`;
                }

                await lineWorksApi.sendTextMessage(userId, resultText).catch(e => console.error(e));
            });
            resolve(null);
        });
    }

    // ------------------------------
    // Geminiとの自然言語チャット処理
    try {
        const sharedContextPath = path.join(__dirname, 'shared_context.txt');
        let sharedContext = "";
        if (fs.existsSync(sharedContextPath)) {
            sharedContext = fs.readFileSync(sharedContextPath, 'utf8');
        }

        const systemInstruction = `あなたは親切な「秘書ちゃん」という優秀なアシスタントです。過去の会話の文脈を踏まえて自然に回答してください。
また、あなたのPC側（開発環境側）のAIから、以下の情報が共有されています。この情報を前提知識として会話してください。
【共有メモ情報】\n` + sharedContext;

        if (!userChats[userId]) {
            userChats[userId] = ai.chats.create({
                model: 'gemini-2.5-flash-lite',
                config: {
                    systemInstruction: systemInstruction
                }
            });
        }

        const chat = userChats[userId];
        console.log("DEBUG: Sending to Gemini...");
        const response = await chat.sendMessage({ message: userMessage });
        console.log("DEBUG: Received from Gemini:", response.text);

        return lineWorksApi.sendTextMessage(userId, response.text);
    } catch (err) {
        console.error("Gemini Error:", err.message || err);
        return lineWorksApi.sendTextMessage(userId, "ごめんなさい、AIの処理中にエラーが発生してしまいました💦");
    }
}

// 5. サーバーの起動とWebhookの設定
const port = process.env.PORT || 3000;
app.listen(port, () => {
    console.log(`秘書ちゃんBotサーバー(LINE WORKS版)がクラウド上で稼働中です！（ポート: ${port}）`);

    // Renderの無料枠（15分でスリープ）を防止するためのセルフPing機能
    // 14分（840,000ミリ秒）ごとに自分自身にリクエストを送る
    setInterval(() => {
        const renderUrl = process.env.RENDER_EXTERNAL_URL;
        if (renderUrl) {
            https.get(`${renderUrl}/webhook`, (resp) => {
                if (resp.statusCode === 200) {
                    console.log('Keep-alive ping successful');
                }
            }).on("error", (err) => {
                console.log("Keep-alive ping failed: " + err.message);
            });
        }
    }, 840000); // 14 minutes
});
