function onSubmit(e) {
  // DiscordのウェブフックURL.
  const webhookURL = 'https://discord.com/api/webhooks/1215867919750402140/6ZbEDuvmesTWR3Rd2fcQPYYAjxErXrHT1mwcyot52VyUSOyc94CBVLqHz4K1UTb9j-kI'; 

  // Discordに表示する文章.
  let messageBody = '';

  messageBody += `フォームに入力がありました。\n`;
  messageBody += `日時:${e.namedValues['タイムスタンプ'][0]}\n`;
  messageBody += `----------\n`;

  // フォームの内容に応じて変える.
  messageBody += `【名前】\n`;
  messageBody += `${e.namedValues['名前'][0]}\n\n`;
  messageBody += `【title】\n`;
  messageBody += `${e.namedValues['title'][0]}\n\n`;
  messageBody += `【URL of the Quotation】\n`;
  messageBody += `${e.namedValues['URL of the Quotation'][0]}\n`;
   messageBody += `【The source, Update date, and Time(引用元・更新日時)】\n`;
  messageBody += `${e.namedValues['The source, Update date, and Time(引用元・更新日時)'][0]}\n\n`;
   messageBody += `【Quoted text(引用本文)】\n`;
  messageBody += `${e.namedValues['Quoted text(引用本文)'][0]}\n\n`;
   messageBody += `【Attachments(添付ファイル)】\n`;
  messageBody += `${e.namedValues['Attachments(添付ファイル)'][0]}\n\n`;
    messageBody += `【Remarks(備考)】\n`;
  messageBody += `${e.namedValues['Remarks(備考)'][0]}\n\n`;
  messageBody += `----------\n`;

  const message = {
    'content': messageBody, 
    'tts': false,
  }

  const param = {
    'method': 'POST',
    'headers': { 'Content-type': 'application/json' },
    'payload': JSON.stringify(message)
  }

  UrlFetchApp.fetch(webhookURL, param);
}

function translateText(text, sourceLang = 'ja', targetLang = 'en') {
  if (!text || text.trim() === '') {
    return text;
  }
  
  try {
    const translatedText = LanguageApp.translate(text, sourceLang, targetLang);
    return translatedText;
  } catch (error) {
    Logger.log('Translation error: ' + error.toString());
    return text; // Return original text if translation fails
  }
}

function askask() {
  shareEvi(2);
}

function shareLatest() {
  shareEvi(SpreadsheetApp.getActive().getSheetByName("Responses").getLastRow())
}

function reshare(){
  for(var i = 203; i <= SpreadsheetApp.getActive().getSheetByName("Responses").getLastRow(); i++) {
    shareEvi(i);
  }
}

function shareEvi(row){
  var data = getData(row);
  //data = [Submitter, Title, tags_AFF(Array), tags_NEG(Array), SourceURL, updateDate, EngSource, Quote, attachment, remark];
  
  var Lsheet = SpreadsheetApp.getActive().getSheetByName("location");  
  var id = Lsheet.getRange(5, 2).getValue(); //最新の全体資料集IDを取る

  //全体資料集に内容を書き込む
  addToDocs(row-2, data, id); //数の調整必要
 
  //通知
  notify(row-2, data);　//数の調整必要
    
  dealPerson(data[0], "Personal Information");
  dealInfo(data[2], "AFF Evi Information");
  dealInfo(data[3], "NEG Evi Information");
  
  refreshForm();
}

function dealPerson(name, sheetName){ //投稿者の名前のみ
  var sheet = SpreadsheetApp.getActive().getSheetByName(sheetName);
  var row = find(name, sheet, 1);
  if(row!=0){　//既存
    var count = sheet.getRange(row, 2).getValue()+1;
    sheet.getRange(row, 2).setValue(count);
  } else {　//０が返ってくる=新規
    sheet.getRange(sheet.getLastRow()+1, 1, 1, 2).setValues([[name, "1"]]);
  }
}

function dealInfo(name, sheetName){  //[[tags, tags, ...], sheetName]
  var sheet = SpreadsheetApp.getActive().getSheetByName(sheetName);

  for(var i = 0; i < name.length; i++){
    var row = find(name[i], sheet, 1);
    if(row!=0){　//既存
      var count = sheet.getRange(row, 2).getValue()+1;
      sheet.getRange(row, 2).setValue(count);
    } else {　//０が返ってくる=新規
      sheet.getRange(sheet.getLastRow()+1, 1, 1, 2).setValues([[name[i], "1"]]);
    }
  }
}

function find(value, sheet, column){
  var lastRow = sheet.getLastRow(); 
  for (var i = 1; i <= lastRow; i++) { 
    var ssValue = sheet.getRange(i, column).getValue();
    if (ssValue == value) {  //全ての既存の物と比較するため、ない場合は新規と見なせる
      return i;
    }
  }
  return 0;
}

function refreshForm() {
  var formId = SpreadsheetApp.getActive().getSheetByName("Location").getRange(1, 2).getValue(); //資料投稿フォームID
  var form = FormApp.openById(formId);
  var itemId = SpreadsheetApp.getActive().getSheetByName("Location").getRange(2, 2, 3).getValues(); //[フォーム投稿者ID, フォームAFFタグID, フォームNEGタグID]
  
  var sheet = SpreadsheetApp.getActive().getSheetByName("Personal Information");
  var option = sheet.getRange(2, 1, sheet.getLastRow()-1).getValues();
  form.getItemById(itemId[0]).asMultipleChoiceItem().setChoiceValues(option).showOtherOption(true);
  
  // 重複を排除する関数
  function removeDuplicates(array) {
    return [...new Set(array)];
  }

  // 選択肢のリストを取得
  let choices = ["Option 1", "Option 2", "Option 1"]; // 重複あり
  choices = removeDuplicates(choices); // 重複を排除

  // Google Formに設定
  formItem.setChoiceValues(choices);
  
  var sheet = SpreadsheetApp.getActive().getSheetByName("AFF Evi Information");
  var option = sheet.getRange(2, 1, sheet.getLastRow()-1).getValues();
  form.getItemById(itemId[1]).asCheckboxItem().setChoiceValues(option).showOtherOption(true);

  var sheet = SpreadsheetApp.getActive().getSheetByName("NEG Evi Information");
  var option = sheet.getRange(2, 1, sheet.getLastRow()-1).getValues();
  form.getItemById(itemId[2]).asCheckboxItem().setChoiceValues(option).showOtherOption(true);  
}

function getData(row){
  var sheet = SpreadsheetApp.getActive().getSheetByName("Responses");
  var data1 = sheet.getRange(row, 2, 1, 2).getValues(); // data1 = [[Submitter, Title]]　data1 = [sub, tit]　×
  var data2 = sheet.getRange(row, 4).getValue();　//AFF tags 　　　ex)) 平等, 質の高い教育
  var data3 = sheet.getRange(row, 5).getValue(); //NEG tags
  var data4 = sheet.getRange(row, 6, 1, 6).getValues(); //data4 = [[SourceURL, updateDate, EngSource, Quote, attachment, remark]]
    
  var data = new Array();
 
  data[0] = data1[0][0]; //Submitter
  data[1] = data1[0][1]; //Title
  data[2] = data2.split(", "); //AFFtags 
  data[3] = data3.split(", "); //NEGtags
  //data = [sub, title, [平等, 質の高い教育], [...]];

  //data4 = [[SourceURL, updateDate, EngSource, Quote, attachment, remark], [...], [...]];
  //data4[0] = [SourceURL, updateDate, EngSource, Quote, attachment, remark];

  //data = [sub, title, [平等, 質の高い教育], [...]];
  //data4[0] = [SourceURL, updateDate, EngSource, Quote, attachment, remark];

  Array.prototype.push.apply(data, data4[0]); //二重括弧取る、残りのdata(array)と結合
  //data = [Submitter, Title,  tags_AFF(Array), tags_NEG(Array), SourceURL, updateDate, EngSource, Quote, attachment, remark];
  return data;
}

function addToDocs(num, data, id){
  //data = [Submitter, Title,  tags_AFF(Array), tags_NEG(Array), SourceURL, updateDate, EngSource, Quote, attachment, remark];
  var doc = DocumentApp.openById(id).getBody();
  doc.appendPageBreak();
  doc.appendParagraph(num + ". " + data[1] + " (" + data[0] + ")")
     .setSpacingBefore(30).setHeading(DocumentApp.ParagraphHeading.HEADING1).setFontSize(12).setBold(true); //Title
  
  var tags = doc.appendParagraph('').setHeading(DocumentApp.ParagraphHeading.NORMAL);
  tags.appendText("#" + data[0]);
  
  if(data[2]!="") {
    tags.appendText(" [AFF]").setForegroundColor('#0000ff');
    for(var i = 0; i < data[2].length; i++) {
      tags.appendText(" #" + data[2][i]).setForegroundColor('#0000ff');
    }
  }

  if(data[3]!="") {
    tags.appendText(" [NEG]").setForegroundColor('#ff0000');
    for(var i = 0; i < data[3].length; i++) {
      tags.appendText(" #" + data[3][i]).setForegroundColor('#ff0000');
    }
  }
  
  //Remark
  if(data[9]!=''){
    doc.appendParagraph('').appendText('※' + data[9]).setFontSize(8).setForegroundColor('#ff00ff');
  }
  
  //attachment
  if(data[8]!="") {
    data[8] = data[8].split(", "); //これで配列に変化する（attachmentが配列化）
    for(var i = 0; i < data[8].length; i++){
      var attachment = DriveApp.getFileById(data[8][i].match(/[-\w]{25,}/)).getBlob();
      //if(attachment.getContentType()!='img') {
        var img = doc.appendImage(attachment);
        var width = img.getWidth();
        var height = img.getHeight();
        if(width>=height) {
          height = height*(500/width);
          width = 500;
        } else {
          width = width*(500/height);
          height = 500;
        }
        img.setWidth(width).setHeight(height);
      //} else {
      //  doc.appendParagraph("添付ファイル：" + data[8]).setBackgroundColor('#ffffff').setLinkUrl(data[8]);
      //}
    }
  }
  
  //表入れ
  var Doc = doc.appendTable();
  
  // Translate the quote from Japanese to English
  var originalQuote = data[7];
  var translatedQuote = translateText(originalQuote, 'ja', 'en');
  
  // Add both original and translated text
  var tableText = "[資料番号:" + num + "] " + data[5] + ": " + data[6] + '\n' + data[4] + '\n\n' + 
                  "【Original (Japanese)】\n" + originalQuote + '\n\n' +
                  "【English Translation】\n" + translatedQuote;
  
  Doc.editAsText().appendText(tableText)
    .setFontSize(11).setForegroundColor('#000000'); //Source;
}

function notify(num, data){
  //data = [Submitter, Title,  tags_AFF(Array), tags_NEG(Array), SourceURL, updateDate, EngSource, Quote, attachment, remark];
  var attachment = "\n添付ファイル：\n";
  var title = "";
  
  //data[8] = attachment
  if(data[8]!=""){
    data[8] = data[8][0];   //?
    data[8] = data[8].split(", "); //  data[8] = "https~~, https~~, https~~"  data[8] = [https~~, https~~, https~~];
    for(var i = 0; i < data[8].length; i++){
      attachment = attachment + data[8][i]; 
      title = "http://drive.google.com/uc?export=view&id=" + data[8][i].match(/[-\w]{25,}/) + ', ';
    }
  } else {
    attachment = "\n" + attachment.replace(/\r?\n/g,"") + "なし";　//この過程で前の変数に入っていた\nを削除する
  }
  
  //data[9] = remark
  if(data[9]!=""){
    data[9] = "\n※" + data[9];
  }
  
  //data[2] = AFF tags
  var tags = "";
  if(data[2]!=""){
    tags += "[AFF]";  //中身変えずに追加する
    for(var i = 0; i < data[2].length; i++){
      tags += "#" + data[2][i] + " ";
    }
  }
  if(data[2]!=""&&data[3]!=""){
    tags += "\n";
  } //&& = かつ
  
  //data[3] = NEG tags
  if(data[3]!=""){
    tags += "[NEG]";
    for(var i = 0; i < data[3].length; i++){
      tags += "#" + data[3][i] + " ";
    }
  }  
  
  //data = [Submitter, Title,  tags_AFF(Array), tags_NEG(Array), SourceURL, updateDate, EngSource, Quote, attachment, remark];

  // Translate the quote for notification
  var originalQuote = data[7];
  var translatedQuote = translateText(originalQuote, 'ja', 'en');
  
  var body = "\n" + tags + "\n\n```" + originalQuote + "```\n\n**English Translation:**\n```" + translatedQuote + "```" + data[9] + attachment + "\n\n【投稿者】" + data[0] + "\n【引用元】" + data[5] + "\n" + data[4];
  GmailApp.sendEmail("trigger@applet.ifttt.com", num + ". " + data[1] + " (" + data[0] + ")", body);
}

function getFormQuestions() {
  // フォームを取得
  const form = FormApp.openById("1gOYYACD2yDS6TbyFXtgTi6gOor_bIG-tpSONnVRTL4U")
  // フォーム内の全アイテム（質問および画像・動画・セクションなど・・・）を取得
  const items = form.getItems()

  for (const item of items) {
    // アイテムの基本的な情報
    console.log(item.getIndex())      // 何番目のアイテムかがわかる
    console.log(item.getId())         // アイテムのID。回答データと紐づける時に使える
    console.log(item.getTitle())      // アイテムのタイトル
    console.log(item.getHelpText())   // アイテムの説明文
    Logger.log(item.getType())
  }
}