require('dotenv').config();
const express = require('express');
const { GoogleGenAI } = require('@google/genai');
const fs = require('fs');
const path = require('path');
const { spawn, exec } = require('child_process');

// LINE WORKS API 用の独自モジュール
const lineWorksApi = require('./lineWorksApi');

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

                console.log("画像の保存が完了しました。Pythonスクリプトを実行します。");

                // 3. Pythonスクリプトの実行
                const scriptPath = path.join(rootDir, '請求書作成', 'App_Core', 'batch_gen.py');
                const workDir = path.dirname(scriptPath);
                const pythonExe = process.env.PYTHON_CMD || 'python';

                exec(`"${pythonExe}" "${scriptPath}"`, { cwd: workDir }, async (error, stdout, stderr) => {
                    if (error) {
                        console.error(`実行エラー: ${error.message}`);
                        console.error(`Python出力 (stdout): ${stdout}`);
                        console.error(`Pythonエラー (stderr): ${stderr}`);
                        const safeErrorMessage = error.message.length > 500 ? error.message.substring(0, 500) + '...' : error.message;
                        await lineWorksApi.sendTextMessage(userId, `【エラー】請求書の作成に失敗しました💦\n${safeErrorMessage}`).catch(e => console.error(e));
                        return resolve(null);
                    }

                    // 4. 最新のPDFを探す
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
                        return resolve(null);
                    }

                    // 5. PDFファイルの直接送信
                    await lineWorksApi.sendTextMessage(userId, "【システム】請求書が完成しました！✨\nPDFファイルを送信します...").catch(e => console.error(e));
                    await lineWorksApi.sendFileMessage(userId, latestPdfPath, foundFilename).catch(err => console.error("Push Error (PDFファイル送信):", err.message || err));

                    // 以降のフロー
                    await lineWorksApi.sendTextMessage(userId, "【システム】元画像を削除しますか？👇\n1: はい\n2: いいえ\n(関係ないメッセージを送るとそのままAIと会話できます)").catch(err => console.error(err));
                    userStates[userId] = { state: 'awaiting_image_delete' };

                    resolve(null);
                });

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

    } else if (userStates[userId] && userStates[userId].state === 'awaiting_dest') {
        if (userMessage === '1' || userMessage === '2') {
            userStates[userId].state = 'awaiting_qty';
            userStates[userId].destChoice = userMessage;
            return lineWorksApi.sendTextMessage(userId, "【システム】ピック依頼の個数を教えてください！（半角数字のみ）");
        } else {
            return lineWorksApi.sendTextMessage(userId, "【システム】エラー: 1 または 2 を入力してください。\n（やめる場合は「キャンセル」と入力）");
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

                    let destName = (destChoice === '1') ? 'ミナミトランスポートレーション' : (destChoice === '2' ? 'TUYOSHI' : 'その他');

                    await lineWorksApi.sendTextMessage(userId, `【システム】${destName}宛 (${qty}個) の請求書が完成しました！✨\nPDFファイルを送信します...`).catch(e => console.error(e));
                    await lineWorksApi.sendFileMessage(userId, latestPdfPath, foundFilename).catch(err => console.error("Push Error (PDF送信):", err.message || err));

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

                exec(`"${pythonExe}" "${scriptPath}" ${cmdArgs}`, { cwd: workDir }, async (error, stdout, stderr) => {
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
        return lineWorksApi.sendTextMessage(userId, "【システム】ピック依頼の請求書を作成します！\n宛先を選択してください：\n\n1: 株式会社ミナミトランスポートレーション\n2: 株式会社TUYOSHI\n\n（半角数字で「1」か「2」を送信してください）");
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

            exec(`"${pythonExe}" "${scriptPath}"`, { cwd: workDir }, async (error, stdout, stderr) => {
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
});
