require('dotenv').config();
const express = require('express');
const { messagingApi, middleware } = require('@line/bot-sdk');
const { GoogleGenAI } = require('@google/genai');
const fs = require('fs');
const path = require('path');
const { spawn, exec } = require('child_process');

// 1. 各種設定情報
const config = {
    channelAccessToken: process.env.LINE_CHANNEL_ACCESS_TOKEN,
    channelSecret: process.env.LINE_CHANNEL_SECRET,
};

// 2. クライアントの準備
const app = express();
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
const client = new messagingApi.MessagingApiClient({
    channelAccessToken: config.channelAccessToken,
});

// ユーザーごとの会話セッションを保存するオブジェクト
const userChats = {};

// 画像処理などの状態管理オブジェクト
const userStates = {};

// 画像の一時保存用ディレクトリ（プロジェクト内に自動作成されます）
const invoiceInDir = path.join(__dirname, 'invoice_in');
const invoiceOutDir = path.join(__dirname, 'invoice_out');

// 3. Webhookエンドポイント（LINEからのメッセージを受け取る場所）
app.post('/webhook', middleware(config), (req, res) => {
    console.log("=== Webhook到達 ===");

    Promise.all(req.body.events.map(handleEvent))
        .then((result) => res.json(result))
        .catch((err) => {
            console.error(err);
            res.status(500).end();
        });
});

// PDFダウンロード用エンドポイント
app.get('/download/:dateFolder/:filename', (req, res) => {
    const dateFolder = req.params.dateFolder;
    const filename = req.params.filename;

    // セキュリティ対策: パストラバーサルを防ぐ
    if (dateFolder.includes('..') || filename.includes('..')) {
        return res.status(403).send('Forbidden');
    }

    const filePath = path.join(invoiceOutDir, dateFolder, filename);

    if (fs.existsSync(filePath)) {
        res.download(filePath, filename); // ファイルをダウンロードさせる
    } else {
        res.status(404).send('ファイルが見つかりません');
    }
});

// 4. メッセージ受信時の処理
async function handleEvent(event) {
    // テキストメッセージまたは画像メッセージ以外は無視する
    if (event.type !== 'message' || (event.message.type !== 'text' && event.message.type !== 'image')) {
        return Promise.resolve(null);
    }

    const userId = event.source.userId;

    // --- 画像メッセージ（請求書作成）の処理 ---
    if (event.message.type === 'image') {
        return new Promise(async (resolve) => {
            console.log("👉 LINEから画像を受信しました！請求書作成を開始します。");

            client.replyMessage({
                replyToken: event.replyToken,
                messages: [{ type: 'text', text: "【システム】レシート画像を認識しました！請求書を作成しています...⏳" }],
            }).catch(e => console.error(e));

            try {
                // 1. 請求書作成依頼フォルダ内を空にする（古い画像を消す）
                if (!fs.existsSync(invoiceInDir)) {
                    fs.mkdirSync(invoiceInDir, { recursive: true });
                }
                const oldFiles = fs.readdirSync(invoiceInDir);
                for (const file of oldFiles) {
                    fs.unlinkSync(path.join(invoiceInDir, file));
                }

                // 2. LINEから画像をダウンロードして保存
                const blobClient = new messagingApi.MessagingApiBlobClient({
                    channelAccessToken: config.channelAccessToken,
                });
                const stream = await blobClient.getMessageContent(event.message.id);
                const imagePath = path.join(invoiceInDir, `${event.message.id}.jpg`);
                const writable = fs.createWriteStream(imagePath);

                if (stream.pipe) {
                    stream.pipe(writable);
                } else {
                    Buffer.from(await stream.arrayBuffer ? await stream.arrayBuffer() : stream).copy(writable)
                    for await (const chunk of stream) {
                        writable.write(chunk);
                    }
                    writable.end();
                }

                writable.on('finish', () => {
                    console.log("画像の保存が完了しました。Pythonスクリプトを実行します。");

                    // 3. Pythonスクリプトの実行
                    // note読者向け：同じフォルダ内に 'python_scripts' フォルダを作り、そこに Python 側の処理を入れる想定です
                    const scriptPath = path.join(__dirname, 'python_scripts', 'invoice_gen.py');
                    const workDir = path.dirname(scriptPath);
                    const pythonExe = 'python'; // ※Mac等の環境によっては 'python3' に変更が必要な場合があります

                    // Pythonスクリプトが存在するか確認
                    if (!fs.existsSync(scriptPath)) {
                        console.error(`エラー: スクリプトが見つかりません -> ${scriptPath}`);
                        client.pushMessage({
                            to: userId,
                            messages: [{ type: 'text', text: `【エラー】Pythonスクリプトが見つかりません💦\n設定を見直してください。` }],
                        }).catch(e => console.error(e));
                        return resolve(null);
                    }

                    exec(`"${pythonExe}" "${scriptPath}"`, { cwd: workDir }, (error, stdout, stderr) => {
                        if (error) {
                            console.error(`実行エラー: ${error}`);
                            client.pushMessage({
                                to: userId,
                                messages: [{ type: 'text', text: `【エラー】請求書の作成に失敗しました💦\n${error.message}` }],
                            }).catch(e => console.error(e));
                            return resolve(null);
                        }

                        // 4. 最新のPDFを探す
                        let latestPdfPath = null;
                        let latestTime = 0;
                        let foundDateFolder = null;
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
                                                foundDateFolder = dFolder;
                                                foundFilename = file;
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        if (!latestPdfPath) {
                            client.pushMessage({
                                to: userId,
                                messages: [{ type: 'text', text: "【システム】スクリプトは成功しましたが、PDFが見つかりませんでした💦" }],
                            }).catch(e => console.error(e));
                            return resolve(null);
                        }

                        // 5. ダウンロードURLの作成と送信
                        const baseUrl = app.locals.tunnelUrl || "http://localhost:3000";
                        const encodedFolder = encodeURIComponent(foundDateFolder);
                        const encodedFile = encodeURIComponent(foundFilename);
                        const downloadUrl = `${baseUrl}/download/${encodedFolder}/${encodedFile}`;

                        client.pushMessage({
                            to: userId,
                            messages: [{
                                type: 'text',
                                text: `【システム】請求書が完成しました！✨\n以下のリンクからダウンロードできます👇\n\n${downloadUrl}`
                            },
                            {
                                type: 'text',
                                text: "【システム】元画像を削除しますか？ (はい/いいえ)"
                            }],
                        }).catch(err => console.error("Push Error (PDF送信):", err.message || err));

                        userStates[userId] = { state: 'awaiting_image_delete' };

                        resolve(null);
                    });
                });

                writable.on('error', (err) => {
                    console.error("画像の保存エラー:", err);
                    client.pushMessage({
                        to: userId,
                        messages: [{ type: 'text', text: "【エラー】画像の保存に失敗しました💦" }],
                    });
                    resolve(null);
                });

            } catch (err) {
                console.error("画像処理エラー:", err);
                client.pushMessage({
                    to: userId,
                    messages: [{ type: 'text', text: "【エラー】処理中に予期せぬエラーが発生しました💦" }],
                });
                resolve(null);
            }
        });
    }

    // 以降はテキストメッセージの処理
    const userMessage = event.message.text;

    // キャンセル処理
    if (userMessage === "キャンセル" && userStates[userId]) {
        delete userStates[userId];
        return client.replyMessage({
            replyToken: event.replyToken,
            messages: [{ type: 'text', text: "【システム】現在の処理をキャンセルしました！" }],
        });
    }

    // 状態に基づいたフロー処理（画像削除の確認）
    if (userStates[userId] && userStates[userId].state === 'awaiting_image_delete') {
        const deleteConfirmed = userMessage === 'はい' || userMessage === 'ハイ' || userMessage.toLowerCase() === 'yes';
        delete userStates[userId]; // 先に状態をクリア

        if (deleteConfirmed) {
            try {
                if (fs.existsSync(invoiceInDir)) {
                    const oldFiles = fs.readdirSync(invoiceInDir);
                    for (const file of oldFiles) {
                        fs.unlinkSync(path.join(invoiceInDir, file));
                    }
                }
                return client.replyMessage({
                    replyToken: event.replyToken,
                    messages: [{ type: 'text', text: "【システム】元画像を削除しました！🗑️" }],
                });
            } catch (err) {
                console.error("画像削除エラー:", err);
                return client.replyMessage({
                    replyToken: event.replyToken,
                    messages: [{ type: 'text', text: "【システム】画像の削除中にエラーが発生しました💦" }],
                });
            }
        } else {
            return client.replyMessage({
                replyToken: event.replyToken,
                messages: [{ type: 'text', text: "【システム】元画像を保持します。📂" }],
            });
        }
    }

    // ------------------------------
    // AIアシスタント（Gemini）処理部分
    // ------------------------------
    try {
        // 共有メモファイルの読み込み（プロンプトに動的な知識を与える）
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
        const response = await chat.sendMessage({ message: userMessage });
        const replyText = response.text;

        // LINEに返事を送信する
        return client.replyMessage({
            replyToken: event.replyToken,
            messages: [{ type: 'text', text: replyText }],
        });
    } catch (err) {
        console.error("Gemini Error:", err.message || err);
        return client.replyMessage({
            replyToken: event.replyToken,
            messages: [{ type: 'text', text: "ごめんなさい、エラーが発生してしまいました💦" }],
        });
    }
}

// 5. サーバーの起動とWebhookの設定
const port = process.env.PORT || 3000;
app.listen(port, () => {
    console.log(`秘書ちゃんBotサーバーが起動しました（ポート: ${port}）`);

    console.log("トンネル(localhost.run)を構築しています...");
    const ssh = spawn('ssh', ['-o', 'StrictHostKeyChecking=no', '-R', `80:localhost:${port}`, 'nokey@localhost.run']);

    let isWebhookSet = false;
    ssh.stdout.on('data', async (data) => {
        const output = data.toString();
        const match = output.match(/https:\/\/[a-zA-Z0-9.-]+\.lhr\.life/);

        if (match && !isWebhookSet) {
            isWebhookSet = true;
            const tunnelUrl = match[0];
            app.locals.tunnelUrl = tunnelUrl; // ハンドラーから参照できるように保存
            console.log(`外部公開URL(localhost.run): ${tunnelUrl}`);

            // LINE側にWebhook URLを自動設定
            const webhookUrl = `${tunnelUrl}/webhook`;
            try {
                await client.setWebhookEndpoint({ endpoint: webhookUrl });
                console.log(`✅ LINEのWebhookに自動で設定しました！: ${webhookUrl}`);
            } catch (err) {
                console.error("Webhook設定エラー:", err.message || err);
                console.log("LINE開発者画面から手動で設定する必要があるかもしれません。");
            }
        }
    });

    ssh.stderr.on('data', (data) => {
        // 接続ログは非表示
    });

    ssh.on('close', () => {
        console.log('トンネルが閉じられました');
    });
});
