require('dotenv').config();
console.log('[1] dotenv OK');
const { Client, GatewayIntentBits, AttachmentBuilder } = require('discord.js');
console.log('[2] discord.js OK');
const { GoogleGenAI } = require('@google/genai');
console.log('[3] genai OK');
const fs = require('fs');
const path = require('path');
const https = require('https');
const { exec, execFile } = require('child_process');
const axios = require('axios');
const express = require('express');
console.log('[4] all imports OK');

// ============================================================
// 設定
// ============================================================
const PORT = process.env.PORT || 3000;
const REQUEST_CHANNEL_ID = '1479786512152531006'; // 📨 作成依頼
const SAVE_CHANNEL_ID    = '1479786536877949110'; // 📁 PDF保存

const rootDir      = path.join(__dirname, '..');
const workDir      = path.join(rootDir, '請求書作成', 'App_Core');
const invoiceOutDir = path.join(rootDir, '請求書作成', '作成済み請求書');

// Gemini
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

// Discord Bot
const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
    ]
});

// 状態管理
const userStates = {};
const userQueues = {};

// ============================================================
// Keep-alive サーバー（Render用）
// ============================================================
const app = express();
app.use(express.json());
app.get('/', (req, res) => res.send('Discord Invoice Bot is running!'));
app.get('/health', (req, res) => res.json({ status: 'ok', uptime: process.uptime() }));
app.listen(PORT, () => console.log(`Keep-alive server: port ${PORT}`));

const RENDER_URL = process.env.RENDER_EXTERNAL_URL;
if (RENDER_URL) {
    setInterval(() => {
        https.get(`${RENDER_URL}/health`).on('error', () => {});
    }, 14 * 60 * 1000);
}

// ============================================================
// ヘルパー関数
// ============================================================
async function sendMsg(channel, text, replyMsg = null) {
    const opts = { content: text };
    if (replyMsg) opts.reply = { messageReference: replyMsg.id, failIfNotExists: false };
    return channel.send(opts).catch(e => console.error('sendMsg error:', e));
}

async function sendPdf(channel, pdfPath, label, replyMsg = null) {
    const filename = path.basename(pdfPath);
    console.log(`PDF送信開始: ${pdfPath} exists=${fs.existsSync(pdfPath)}`);
    // 作成依頼チャンネルに送信
    try {
        const opts = {
            content: `📄 ${label}`,
            files: [new AttachmentBuilder(pdfPath, { name: filename })]
        };
        if (replyMsg) opts.reply = { messageReference: replyMsg.id, failIfNotExists: false };
        await channel.send(opts);
        console.log('作成依頼チャンネル送信完了');
    } catch (e) {
        console.error('作成依頼チャンネル送信エラー:', e.message);
    }
    // PDF保存チャンネルにも送信
    try {
        const saveChannel = await client.channels.fetch(SAVE_CHANNEL_ID);
        await saveChannel.send({
            content: `📄 ${label}`,
            files: [new AttachmentBuilder(pdfPath, { name: filename })]
        });
        console.log('PDF保存チャンネル送信完了');
    } catch (e) {
        console.error('PDF保存チャンネル送信エラー:', e.message, 'channel:', SAVE_CHANNEL_ID);
    }
}

async function downloadImage(url, localPath) {
    const response = await axios.get(url, { responseType: 'arraybuffer' });
    fs.writeFileSync(localPath, Buffer.from(response.data));
}

function runPython(scriptPath, args, cwd) {
    const pythonExe = process.env.PYTHON_CMD || 'python';
    return new Promise((resolve, reject) => {
        execFile(pythonExe, [scriptPath, ...args], { cwd, env: { ...process.env } }, (error, stdout, stderr) => {
            if (error) reject({ error, stderr });
            else resolve(stdout);
        });
    });
}

function finishAndProcessNext(userId) {
    delete userStates[userId];
    if (userQueues[userId] && userQueues[userId].length > 0) {
        const next = userQueues[userId].shift();
        processImageItem(userId, next.attachmentUrl, next.channel, next.originalMsg);
    }
}

// ============================================================
// 画像OCRフロー
// ============================================================
async function processImageItem(userId, attachmentUrl, channel, originalMsg) {
    userStates[userId] = { state: 'awaiting_doc_type', attachmentUrl, channel, originalMsg };
    await sendMsg(channel, '【システム】画像を受け取りました！\n作成する書類を選択してください👇\n1: 請求書\n2: お支払い通知書', originalMsg);
}

async function processImageOCR(userId) {
    const { attachmentUrl, channel, originalMsg, docType } = userStates[userId];
    await sendMsg(channel, '【システム】画像を読み取っています...⏳');

    try {
        const tmpPath = path.join(workDir, `tmp_ocr_${userId}_${Date.now()}.jpg`);
        await downloadImage(attachmentUrl, tmpPath);

        const base64Image = fs.readFileSync(tmpPath).toString('base64');
        fs.unlinkSync(tmpPath);

        const prompt = `この画像は運送業の請求書またはレシートです。画像に含まれる全ての明細行を一行も省略せずに全て抽出してください。
各行の作業内容・単価（調整前の元の値）・数量を特定してください。

以下のJSON形式のみで返してください:
{"items": [{"name": "作業内容", "unit": 元の単価の数値, "qty": 数量}]}`;

        const response = await ai.models.generateContent({
            model: 'gemini-2.5-flash',
            contents: [{ parts: [
                { text: prompt },
                { inlineData: { mimeType: 'image/jpeg', data: base64Image } }
            ]}]
        });

        const rawText = response.candidates[0].content.parts[0].text;
        const jsonMatch = rawText.match(/\{[\s\S]*\}/);
        if (!jsonMatch) throw new Error('JSONが見つかりませんでした');

        const parsed = JSON.parse(jsonMatch[0]);
        const items = parsed.items.map(item => {
            let unit = parseInt(String(item.unit).replace(/[^0-9\-]/g, ''), 10) || 0;
            const qty  = parseInt(String(item.qty).replace(/[^0-9]/g, ''), 10) || 1;
            // 単価調整（プログラムで実施）
            if (unit > 0) {
                if (docType === 'payment') {
                    unit = unit >= 20000 ? unit - 100 : unit - 50;
                } else {
                    unit = unit >= 20000 ? unit - 100 : unit - 20;
                }
            }
            return { name: item.name, unit, qty, total: unit * qty };
        });

        const total = items.reduce((s, it) => s + it.total, 0);
        const docLabel = docType === 'payment' ? '支払い通知書' : '請求書';
        let confirmText = '【システム】以下の内容で読み取りました：\n\n';
        items.forEach((it, i) => {
            confirmText += `${i+1}. ${it.name}\n   ¥${it.unit.toLocaleString()} × ${it.qty}個 = ¥${it.total.toLocaleString()}\n`;
        });
        confirmText += `\n合計金額: ¥${total.toLocaleString()}\n\nこの内容で${docLabel}を作成してもよろしいですか？👇\n1: はい\n2: キャンセル\n\n【修正がある場合】\n「たまごっち 6,200円 1個 が抜けてるよ！」のようにメッセージを送ってください。`;

        userStates[userId] = { ...userStates[userId], state: 'awaiting_ocr_confirm', invoiceData: { items } };
        await sendMsg(channel, confirmText);
    } catch (e) {
        console.error('OCRエラー:', e);
        await sendMsg(channel, `【エラー】画像の読み取りに失敗しました💦\n${e.message || '不明なエラー'}`);
        finishAndProcessNext(userId);
    }
}

// ============================================================
// メインメッセージハンドラ
// ============================================================
client.on('messageCreate', async (message) => {
    if (message.author.bot) return;
    if (message.channelId !== REQUEST_CHANNEL_ID) return;

    const userId = message.author.id;
    const userMessage = message.content.trim();
    const channel = message.channel;

    // ---- キャンセル ----
    if (userMessage === 'キャンセル') {
        if (userStates[userId]) {
            finishAndProcessNext(userId);
            return sendMsg(channel, '【システム】操作をキャンセルしました。', message);
        }
        return;
    }

    // ---- 画像添付 ----
    if (message.attachments.size > 0) {
        const images = [...message.attachments.values()].filter(a => a.contentType?.startsWith('image/'));
        if (images.length > 0) {
            for (const img of images) {
                if (userStates[userId]?.state) {
                    if (!userQueues[userId]) userQueues[userId] = [];
                    userQueues[userId].push({ attachmentUrl: img.url, channel, originalMsg: message });
                    await sendMsg(channel, `【システム】キューに追加しました（待ち: ${userQueues[userId].length}件）`, message);
                } else {
                    await processImageItem(userId, img.url, channel, message);
                }
            }
            return;
        }
    }

    const st = userStates[userId];
    const state = st?.state;

    // ============================================================
    // OCRフロー状態管理
    // ============================================================

    // 書類タイプ選択
    if (state === 'awaiting_doc_type') {
        if (userMessage === '1') {
            userStates[userId].docType = 'invoice';
            return processImageOCR(userId);
        } else if (userMessage === '2') {
            userStates[userId].docType = 'payment';
            userStates[userId].state = 'awaiting_payment_dest';
            return sendMsg(channel, '【システム】宛先を選択してください👇\n1: ちなじゅん運送\n2: それ以外');
        }
        return sendMsg(channel, '【システム】1 または 2 を送信してください。');
    }

    // 支払い宛先選択
    if (state === 'awaiting_payment_dest') {
        if (userMessage === '1') {
            userStates[userId] = { ...st, paymentDestType: 'chinajun', paymentDestName: 'ちなじゅん運送 井後陽輔' };
            return processImageOCR(userId);
        } else if (userMessage === '2') {
            userStates[userId] = { ...st, paymentDestType: 'other', state: 'awaiting_payment_dest_name' };
            return sendMsg(channel, '【システム】宛先の会社名を入力してください');
        }
        return sendMsg(channel, '【システム】1 または 2 を送信してください。');
    }

    // 宛先名入力
    if (state === 'awaiting_payment_dest_name') {
        userStates[userId] = { ...st, paymentDestName: userMessage };
        return processImageOCR(userId);
    }

    // OCR確認
    if (state === 'awaiting_ocr_confirm') {
        const { invoiceData, docType, paymentDestType, paymentDestName } = st;

        if (userMessage === '1') {
            userStates[userId].state = 'processing';
            await sendMsg(channel, '【システム】承知しました！PDFを作成しています...⏳');

            let scriptPath, scriptArgs;
            if (docType === 'payment') {
                scriptPath = path.join(workDir, 'payment_notice.py');
                scriptArgs = ['--payment-json', JSON.stringify({ destType: paymentDestType, destName: paymentDestName, items: invoiceData.items })];
            } else {
                // batch_gen.py には deadline が必須（OCRフローはデフォルト1週間後）
                const deadline = new Date();
                deadline.setDate(deadline.getDate() + 7);
                const invoicePayload = { ...invoiceData, deadline: deadline.toISOString() };
                scriptPath = path.join(workDir, 'batch_gen.py');
                scriptArgs = ['--generate-from-json', JSON.stringify(invoicePayload)];
            }

            try {
                const stdout = await runPython(scriptPath, scriptArgs, workDir);
                const pdfMatch = stdout.match(/___PDF_GENERATED___:(.+)/);
                if (!pdfMatch) throw new Error('PDFパスが見つかりません\n' + stdout);
                const pdfPath = pdfMatch[1].trim();
                const completedLabel = docType === 'payment' ? '支払い通知書' : '請求書';
                await sendPdf(channel, pdfPath, `${completedLabel}：${path.basename(pdfPath)}`, st.originalMsg);
                await sendMsg(channel, `✅ ${completedLabel}が完成しました！`);
                finishAndProcessNext(userId);
            } catch (e) {
                console.error('PDF生成エラー:', e);
                await sendMsg(channel, `【エラー】PDF生成に失敗しました💦\n${e.stderr?.substring(0, 300) || e.error?.message || String(e)}`);
                finishAndProcessNext(userId);
            }
            return;
        }

        if (userMessage === '2') {
            finishAndProcessNext(userId);
            return sendMsg(channel, '【システム】キャンセルしました。');
        }

        // 修正指示（AIで再解釈）
        const fixMatch = userMessage.match(/(.+?)\s+([\d,]+)円\s*(\d+)(個|枚|台|件)?/);
        if (fixMatch) {
            const unit = parseInt(fixMatch[2].replace(/,/g, ''), 10);
            const qty  = parseInt(fixMatch[3], 10);
            invoiceData.items.push({ name: fixMatch[1].trim(), unit, qty, total: unit * qty });
            const total = invoiceData.items.reduce((s, it) => s + it.total, 0);
            const docLabel = docType === 'payment' ? '支払い通知書' : '請求書';
            let confirmText = '【システム】追加しました！更新内容：\n\n';
            invoiceData.items.forEach((it, i) => {
                confirmText += `${i+1}. ${it.name} ¥${it.unit.toLocaleString()} × ${it.qty}個 = ¥${it.total.toLocaleString()}\n`;
            });
            confirmText += `\n合計金額: ¥${total.toLocaleString()}\n\nこの内容で${docLabel}を作成してもよろしいですか？\n1: はい\n2: キャンセル`;
            userStates[userId].invoiceData = invoiceData;
            return sendMsg(channel, confirmText);
        }
        return sendMsg(channel, '【システム】1: はい / 2: キャンセル を送信するか、修正内容を「〇〇 6,200円 1個」の形式で送ってください。');
    }

    // ============================================================
    // 手動請求書作成フロー
    // ============================================================

    if (state === 'awaiting_manual_dest') {
        userStates[userId] = { state: 'awaiting_manual_content', manualDest: userMessage, manualItems: [] };
        return sendMsg(channel, '【システム】内容を教えてください');
    }

    if (state === 'awaiting_manual_content') {
        userStates[userId] = { ...st, state: 'awaiting_manual_price', manualContent: userMessage };
        return sendMsg(channel, '【システム】金額（単価）を半角数字で教えてください');
    }

    if (state === 'awaiting_manual_price') {
        const price = parseInt(userMessage, 10);
        if (!isNaN(price) && price >= 0) {
            userStates[userId] = { ...st, state: 'awaiting_manual_qty', manualPrice: price };
            return sendMsg(channel, '【システム】個数を半角数字で教えてください');
        }
        return sendMsg(channel, '【システム】有効な数字を入力してください。');
    }

    if (state === 'awaiting_manual_qty') {
        const qty = parseInt(userMessage, 10);
        if (!isNaN(qty) && qty > 0) {
            const item = { name: st.manualContent, unit: st.manualPrice, qty, total: st.manualPrice * qty };
            userStates[userId] = { ...st, state: 'awaiting_manual_more', pendingItem: item };
            return sendMsg(channel, `【システム】1品目を追加しました✅\n・${item.name} ¥${item.unit.toLocaleString()} × ${qty}個 = ¥${item.total.toLocaleString()}\n\n次の項目を追加しますか？\n1: 追加する\n2: これで完了（消費税確認へ）`);
        }
        return sendMsg(channel, '【システム】有効な数字（1以上）を入力してください。');
    }

    if (state === 'awaiting_manual_more') {
        if (userMessage === '1') {
            st.manualItems.push(st.pendingItem);
            userStates[userId] = { ...st, state: 'awaiting_manual_content' };
            return sendMsg(channel, '【システム】次の項目を入力してください。\n内容を教えてください');
        } else if (userMessage === '2') {
            st.manualItems.push(st.pendingItem);
            const items = st.manualItems;
            userStates[userId] = { ...st, state: 'awaiting_manual_tax' };
            const summary = items.map((it, i) => `${i+1}. ${it.name} ${it.qty}個 ¥${it.unit.toLocaleString()}`).join('\n');
            return sendMsg(channel, `【システム】合計${items.length}品目の入力が完了しました！\n\n${summary}\n\n税込みですか？税抜きですか？\n1: 税込み\n2: 税抜き`);
        }
        return sendMsg(channel, '【システム】1 か 2 を送信してください。');
    }

    if (state === 'awaiting_manual_tax') {
        if (userMessage === '1' || userMessage === '2') {
            userStates[userId] = { ...st, state: 'awaiting_manual_deadline', manualTaxType: userMessage };
            return sendMsg(channel, '【システム】支払い期日を選択してください👇\n1: 作成日から1週間後\n2: 当月末\n3: 翌月末');
        }
        return sendMsg(channel, '【システム】1 または 2 を入力してください。');
    }

    if (state === 'awaiting_manual_deadline') {
        if (['1', '2', '3'].includes(userMessage)) {
            userStates[userId] = { ...st, state: 'processing' };
            await sendMsg(channel, '【システム】承知しました！請求書を作成しています...⏳');
            const payload = JSON.stringify({ dest: st.manualDest, items: st.manualItems, taxType: st.manualTaxType, deadlineType: userMessage });
            try {
                const stdout = await runPython(path.join(workDir, 'manual_invoice.py'), ['--items-json', payload], workDir);
                const pdfMatch = stdout.match(/___PDF_GENERATED___:(.+)/);
                if (!pdfMatch) throw new Error('PDFパスが見つかりません');
                const pdfPath = pdfMatch[1].trim();
                await sendPdf(channel, pdfPath, `請求書：${path.basename(pdfPath)}`);
                await sendMsg(channel, `✅ ${st.manualDest}御中の請求書が完成しました！`);
                delete userStates[userId];
            } catch (e) {
                console.error('手動請求書エラー:', e);
                await sendMsg(channel, `【エラー】請求書の作成に失敗しました💦\n${e.stderr?.substring(0, 300) || e.error?.message || String(e)}`);
                delete userStates[userId];
            }
            return;
        }
        return sendMsg(channel, '【システム】1・2・3 のいずれかを送信してください。');
    }

    // ============================================================
    // ピック依頼フロー
    // ============================================================

    if (state === 'awaiting_dest') {
        if (['1', '2', '3', '4'].includes(userMessage)) {
            userStates[userId] = { state: 'awaiting_qty', destChoice: userMessage };
            return sendMsg(channel, '【システム】ピック依頼の個数を教えてください！（半角数字のみ）');
        }
        return sendMsg(channel, '【システム】1 から 4 のいずれかを入力してください。');
    }

    if (state === 'awaiting_qty') {
        const qty = parseInt(userMessage, 10);
        if (!isNaN(qty) && qty > 0) {
            const { destChoice } = st;
            userStates[userId] = { state: 'processing' };
            await sendMsg(channel, '【システム】個数を承知しました！請求書を作成しています...⏳');

            const scriptPath = path.join(workDir, '..', 'App_Core', 'pick_invoice.py');
            const pythonExe = process.env.PYTHON_CMD || 'python';
            exec(`"${pythonExe}" "${scriptPath}" ${destChoice} ${qty}`, { cwd: workDir }, async (error, stdout, stderr) => {
                if (error) {
                    await sendMsg(channel, `【エラー】ピック用請求書の作成に失敗しました💦\n${error.message}`);
                    delete userStates[userId];
                    return;
                }
                // 最新PDFを探す
                let latestPdfPath = null, latestTime = 0;
                const searchDirs = (dir) => {
                    for (const entry of fs.readdirSync(dir)) {
                        const p = path.join(dir, entry);
                        if (fs.statSync(p).isDirectory()) searchDirs(p);
                        else if (entry.endsWith('.pdf')) {
                            const t = fs.statSync(p).mtimeMs;
                            if (t > latestTime) { latestTime = t; latestPdfPath = p; }
                        }
                    }
                };
                if (fs.existsSync(invoiceOutDir)) searchDirs(invoiceOutDir);

                if (!latestPdfPath) {
                    await sendMsg(channel, '【システム】PDFが見つかりませんでした💦');
                    delete userStates[userId];
                    return;
                }
                const destNames = { '1': 'ミナミトランスポートレーション', '2': 'TUYOSHI', '3': '株式会社りんご', '4': '寺本康太' };
                const destName = destNames[destChoice] || 'その他';
                await sendPdf(channel, latestPdfPath, `請求書：${path.basename(latestPdfPath)}`);
                await sendMsg(channel, `✅ ${destName}宛 (${qty}個) の請求書が完成しました！🧾`);
                delete userStates[userId];
            });
            return;
        }
        return sendMsg(channel, '【システム】有効な数字（1以上）を入力してください。');
    }

    // ============================================================
    // トリガーコマンド
    // ============================================================

    if (userMessage === '請求書作成') {
        userStates[userId] = { state: 'awaiting_manual_dest' };
        return sendMsg(channel, '【システム】手動で請求書を作成します！\n宛先の会社名を入力してください', message);
    }

    if (userMessage === 'ピック依頼') {
        userStates[userId] = { state: 'awaiting_dest' };
        return sendMsg(channel, '【システム】ピック依頼の請求書を作成します！\n宛先を選択してください：\n\n1: 株式会社ミナミトランスポートレーション\n2: 株式会社TUYOSHI\n3: 株式会社りんご\n4: 寺本康太\n\n（半角数字で送信してください）', message);
    }

    if (userMessage === 'ヘルプ' || userMessage === 'help') {
        return sendMsg(channel, '【システム】使い方👇\n\n📸 **画像を貼る** → 請求書 or 支払い通知書を自動作成\n\n✏️ **テキストコマンド**\n・`請求書作成` → 手動で請求書を作成\n・`ピック依頼` → ピック依頼用請求書を作成\n・`キャンセル` → 操作を中断', message);
    }
});

// ============================================================
// Bot起動
// ============================================================
client.once('ready', () => {
    console.log(`✅ Discord Bot起動: ${client.user.tag}`);
    console.log(`📨 作成依頼チャンネル: ${REQUEST_CHANNEL_ID}`);
    console.log(`📁 PDF保存チャンネル:  ${SAVE_CHANNEL_ID}`);
});

const token = process.env.DISCORD_BOT_TOKEN;
console.log('DISCORD_BOT_TOKEN:', token ? `設定済み(${token.length}文字)` : '★未設定★');
console.log('Node.js version:', process.version);

process.on('uncaughtException', (e) => console.error('★ uncaughtException:', e.message));
process.on('unhandledRejection', (e) => console.error('★ unhandledRejection:', e?.message || e));

client.on('error', (e) => console.error('★ Discord client error:', e.message));
client.on('warn', (msg) => console.warn('Discord warn:', msg));
client.on('debug', (msg) => { if (msg.includes('Identified') || msg.includes('READY') || msg.includes('error') || msg.includes('Error')) console.log('Discord debug:', msg); });

if (!token) {
    console.error('★ DISCORD_BOT_TOKEN が未設定です');
} else {
    console.log('Discord login 開始...');
    const loginTimer = setTimeout(() => {
        console.error('★ Discord login 30秒タイムアウト！WebSocket接続がブロックされている可能性があります');
    }, 30000);

    client.login(token)
        .then(() => {
            clearTimeout(loginTimer);
            console.log('Discord login Promise resolved ✅');
        })
        .catch(e => {
            clearTimeout(loginTimer);
            console.error('★ Discord Bot ログイン失敗:', e.message);
            console.error('スタック:', e.stack?.substring(0, 500));
        });
}
