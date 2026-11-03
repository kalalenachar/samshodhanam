if(typeof keyman === 'undefined') {
  console.log('Keyboard requires KeymanWeb 10.0 or later');
  if(typeof tavultesoft !== 'undefined') tavultesoft.keymanweb.util.alert("This keyboard requires KeymanWeb 10.0 or later");
} else {
KeymanWeb.KR(new Keyboard_itrans_devanagari_sanskrit_vedic());
}
function Keyboard_itrans_devanagari_sanskrit_vedic()
{
  var modCodes = keyman.osk.modifierCodes;
  var keyCodes = keyman.osk.keyCodes;

  this.KI="Keyboard_itrans_devanagari_sanskrit_vedic";
  this.KN="Vedic Sanskrit Devanagari Phonetic (ITRANS)";
  this.KMINVER="10.0";
  this.KV={F:' 1em "FreeSerif"',K102:0};
  this.KV.KLS={
    "rightalt": ["᳐","᳑","᳒","᳓","᳔","᳕","᳖","᳗","᳘","᳙","","ꣻ","ꣽ","","","","᳣","᳤","᳥","᳦","ᳪ","ᳫ","᳴","ᳮ","ᳯ","ᳰ","꣸","꣹","꣺","","","","᳧","᳨","ᳱ","᳜","ᳩ","ᳬ","","","ꣷ","ꣵ","ꣶ","","","","","","","᳢","ᳵ","᳝","᳸","᳹","᳠","᳢","ꣲ","ꣳ","ꣴ","","","","","",""],
    "rightctrl": ["","꣡","꣢","꣣","꣤","꣥","꣦","꣧","꣢꣯","꣢꣫","꣣꣬","","","","","","","","","꣯","","","꣫","","","꣮","꣸","꣹","꣼","","","","꣪","꣱","","","","","","꣬","","꣺","ꣻ","","","","","","","᳸","᳹","᳒","꣰","","꣭","","᳐","᳑","᳓","","","","","",""],
    "default": ["`","१","२","३","४","५","६","७","८","९","०","-","=","","","","ॳ","व्","ए","र्","त्","य्","उ","इ","ओ","प्","ऎ","ऒ","\\","","","","अ","स्","द्","फ्","ग्","ह्","ज्","क्","ल्",";","'","","","","","","","ॶ","क्ष्","च्","व्","ब्","न्","म्",",",".","/","","","","","",""],
    "shift": ["~","!","@","ॐ","₹","࿕","्","☸","❀","(",")","‌","‍","","","","ॴ","ऄ","ऍ","र्‍","ट्","ञ्","ऊ","ई","ऑ","फ्","ꣾ","ॵ","|","","","","आ","ष्","ड्","ङ्","घ्","ः","झ्","ख्","ळ्",":","\"","","","","","","","ॷ","ज्ञ्","छ्","ऽ","भ्","ण्","ं","<",">","?","","","","","",""]
  };
  this.KV.BK=(function(x){
    var
      empty=Array.apply(null, Array(65)).map(String.prototype.valueOf,""),
      result=[], v, i,
      modifiers=['default','shift','ctrl','shift-ctrl','alt','shift-alt','ctrl-alt','shift-ctrl-alt'];
    for(i=modifiers.length-1;i>=0;i--) {
      v = x[modifiers[i]];
      if(v || result.length > 0) {
        result=(v ? v : empty).slice().concat(result);
      }
    }
    return result;
  })(this.KV.KLS);
  this.KDU=1;
  this.KH="Uses Unshifted, Shifted, Right Alt and Right Ctrl layouts.";
  this.KM=0;
  this.KBVER="1.2.1";
  this.KMBM=modCodes.RCTRL | modCodes.RALT | modCodes.SHIFT /* 0x001A */;
  this.s_opt1=KeymanWeb.KLOAD(this.KI,"opt1","0");
  this.s_Punctuation="!'()-/:;?`\",.=\\<>|";
  this.s_Digits="0123456789";
  this.s_DigitsU="०१२३४५६७८९";
  this.s_Vyanjana="कक्षखगघङचछजज्ञझञटठडढणतथदधनपफबभमयरलळवश्रषसह";
  this.s_NuktaVyanjana="कखगजझडढफनरळय";
  this.s_ViramaMaatraa="eiouAEIORU[]LW{}qQzZ";
  this.s_ViramaMaatraaU="ेिोुाॅीॉृूॆॊॢॆꣿॏऺऻॖॗ";
  this.s_aPlusMaatraa="aeiuw";
  this.s_aPlusMaatraaU="ाॅैौॉ";
  this.s_opt1endings="!'()-/:;?`\",.=\\<>| ";
  this.s25="hindi";
  this.s26="0";
  this.s27="0";
  this.s28="0";
  this.s29="0";
  this.s30="0";
  this.s31="hindi";
  this.s32="hindi";
  this.KVER="11.0.1356.0";
  this.gs=function(t,e) {
    return this.g_main(t,e);
  };
  this.g_main=function(t,e) {
    var k=KeymanWeb,r=0,m=0;
    if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_BKSP /* 0x08 */)) {
      if(k.KFCM(1,t,[{t:'a',a:this.s_DigitsU}])){
        r=m=1;   // Line 108
        k.KDC(1,t);
        k.KIO(-1,this.s_Digits,1,t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_C /* 0x43 */)) {
      if(k.KFCM(1,t,['᳝'])){
        r=m=1;   // Line 385
        k.KDC(1,t);
        k.KO(-1,t,"᳞");
      }
      else if(k.KFCM(1,t,['᳞'])){
        r=m=1;   // Line 386
        k.KDC(1,t);
        k.KO(-1,t,"᳟");
      }
      else if(1){
        r=m=1;   // Line 384
        k.KDC(0,t);
        k.KO(-1,t,"᳝");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x400A */, keyCodes.K_1 /* 0x31 */)) {
      if(1){
        r=m=1;   // Line 71
        k.KDC(0,t);
        this.s_opt1=this.s25;
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x400A */, keyCodes.K_0 /* 0x30 */)) {
      if(1){
        r=m=1;   // Line 72
        k.KDC(0,t);
        this.s_opt1=k.KLOAD(this.KI,"opt1","0");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_1 /* 0x31 */)) {
      if(1){
        r=m=1;   // Line 356
        k.KDC(0,t);
        k.KO(-1,t,"᳑");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_2 /* 0x32 */)) {
      if(1){
        r=m=1;   // Line 357
        k.KDC(0,t);
        k.KO(-1,t,"᳒");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_3 /* 0x33 */)) {
      if(1){
        r=m=1;   // Line 358
        k.KDC(0,t);
        k.KO(-1,t,"᳓");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_4 /* 0x34 */)) {
      if(1){
        r=m=1;   // Line 359
        k.KDC(0,t);
        k.KO(-1,t,"᳔");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_5 /* 0x35 */)) {
      if(1){
        r=m=1;   // Line 360
        k.KDC(0,t);
        k.KO(-1,t,"᳕");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_6 /* 0x36 */)) {
      if(1){
        r=m=1;   // Line 361
        k.KDC(0,t);
        k.KO(-1,t,"᳖");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_7 /* 0x37 */)) {
      if(1){
        r=m=1;   // Line 362
        k.KDC(0,t);
        k.KO(-1,t,"᳗");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_8 /* 0x38 */)) {
      if(1){
        r=m=1;   // Line 363
        k.KDC(0,t);
        k.KO(-1,t,"᳘");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_9 /* 0x39 */)) {
      if(1){
        r=m=1;   // Line 364
        k.KDC(0,t);
        k.KO(-1,t,"᳙");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_A /* 0x41 */)) {
      if(1){
        r=m=1;   // Line 365
        k.KDC(0,t);
        k.KO(-1,t,"᳧");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_BKQUOTE /* 0xC0 */)) {
      if(1){
        r=m=1;   // Line 366
        k.KDC(0,t);
        k.KO(-1,t,"᳐");
      }
      else if(1){
        r=m=1;   // Line 393
        k.KDC(0,t);
        k.KO(-1,t,"꣼");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_D /* 0x44 */)) {
      if(1){
        r=m=1;   // Line 367
        k.KDC(0,t);
        k.KO(-1,t,"ᳱ");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_E /* 0x45 */)) {
      if(1){
        r=m=1;   // Line 368
        k.KDC(0,t);
        k.KO(-1,t,"᳥");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_G /* 0x47 */)) {
      if(1){
        r=m=1;   // Line 369
        k.KDC(0,t);
        k.KO(-1,t,"ᳩ");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_H /* 0x48 */)) {
      if(1){
        r=m=1;   // Line 370
        k.KDC(0,t);
        k.KO(-1,t,"ᳬ");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_I /* 0x49 */)) {
      if(1){
        r=m=1;   // Line 371
        k.KDC(0,t);
        k.KO(-1,t,"ᳮ");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_O /* 0x4F */)) {
      if(1){
        r=m=1;   // Line 372
        k.KDC(0,t);
        k.KO(-1,t,"ᳯ");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_P /* 0x50 */)) {
      if(1){
        r=m=1;   // Line 373
        k.KDC(0,t);
        k.KO(-1,t,"ᳰ");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_Q /* 0x51 */)) {
      if(1){
        r=m=1;   // Line 374
        k.KDC(0,t);
        k.KO(-1,t,"᳣");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_R /* 0x52 */)) {
      if(1){
        r=m=1;   // Line 375
        k.KDC(0,t);
        k.KO(-1,t,"᳦");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_S /* 0x53 */)) {
      if(1){
        r=m=1;   // Line 376
        k.KDC(0,t);
        k.KO(-1,t,"᳨");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_T /* 0x54 */)) {
      if(1){
        r=m=1;   // Line 377
        k.KDC(0,t);
        k.KO(-1,t,"ᳪ");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_U /* 0x55 */)) {
      if(1){
        r=m=1;   // Line 378
        k.KDC(0,t);
        k.KO(-1,t,"᳴");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_W /* 0x57 */)) {
      if(1){
        r=m=1;   // Line 379
        k.KDC(0,t);
        k.KO(-1,t,"᳤");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_X /* 0x58 */)) {
      if(1){
        r=m=1;   // Line 380
        k.KDC(0,t);
        k.KO(-1,t,"ᳵ");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_Y /* 0x59 */)) {
      if(1){
        r=m=1;   // Line 381
        k.KDC(0,t);
        k.KO(-1,t,"ᳫ");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_Z /* 0x5A */)) {
      if(1){
        r=m=1;   // Line 382
        k.KDC(0,t);
        k.KO(-1,t,"᳢");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_B /* 0x42 */)) {
      if(1){
        r=m=1;   // Line 383
        k.KDC(0,t);
        k.KO(-1,t,"᳹");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_F /* 0x46 */)) {
      if(1){
        r=m=1;   // Line 387
        k.KDC(0,t);
        k.KO(-1,t,"᳜");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_M /* 0x4D */)) {
      if(1){
        r=m=1;   // Line 388
        k.KDC(0,t);
        k.KO(-1,t,"᳢");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_N /* 0x4E */)) {
      if(1){
        r=m=1;   // Line 389
        k.KDC(0,t);
        k.KO(-1,t,"᳠");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_V /* 0x56 */)) {
      if(1){
        r=m=1;   // Line 390
        k.KDC(0,t);
        k.KO(-1,t,"᳸");
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_HYPHEN /* 0xBD */)) {
      if(1){
        r=m=1;   // Line 394
        k.KDC(0,t);
        k.KO(-1,t,"ꣻ");
      }
      else if(1){
        r=m=1;   // Line 411
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_EQUAL /* 0xBB */)) {
      if(1){
        r=m=1;   // Line 395
        k.KDC(0,t);
        k.KO(-1,t,"ꣽ");
      }
      else if(1){
        r=m=1;   // Line 410
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_BKSLASH /* 0xDC */)) {
      if(1){
        r=m=1;   // Line 396
        k.KDC(0,t);
        k.KO(-1,t,"꣺");
      }
      else if(1){
        r=m=1;   // Line 407
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_RBRKT /* 0xDD */)) {
      if(1){
        r=m=1;   // Line 397
        k.KDC(0,t);
        k.KO(-1,t,"꣹");
      }
      else if(1){
        r=m=1;   // Line 416
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_LBRKT /* 0xDB */)) {
      if(1){
        r=m=1;   // Line 398
        k.KDC(0,t);
        k.KO(-1,t,"꣸");
      }
      else if(1){
        r=m=1;   // Line 412
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_L /* 0x4C */)) {
      if(1){
        r=m=1;   // Line 399
        k.KDC(0,t);
        k.KO(-1,t,"ꣷ");
      }
      else if(1){
        r=m=1;   // Line 413
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_QUOTE /* 0xDE */)) {
      if(1){
        r=m=1;   // Line 400
        k.KDC(0,t);
        k.KO(-1,t,"ꣶ");
      }
      else if(1){
        r=m=1;   // Line 415
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_COLON /* 0xBA */)) {
      if(1){
        r=m=1;   // Line 401
        k.KDC(0,t);
        k.KO(-1,t,"ꣵ");
      }
      else if(1){
        r=m=1;   // Line 408
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_SLASH /* 0xBF */)) {
      if(1){
        r=m=1;   // Line 402
        k.KDC(0,t);
        k.KO(-1,t,"ꣴ");
      }
      else if(1){
        r=m=1;   // Line 417
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_PERIOD /* 0xBE */)) {
      if(1){
        r=m=1;   // Line 403
        k.KDC(0,t);
        k.KO(-1,t,"ꣳ");
      }
      else if(1){
        r=m=1;   // Line 414
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_COMMA /* 0xBC */)) {
      if(1){
        r=m=1;   // Line 404
        k.KDC(0,t);
        k.KO(-1,t,"ꣲ");
      }
      else if(1){
        r=m=1;   // Line 409
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_0 /* 0x30 */)) {
      if(1){
        r=m=1;   // Line 406
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_J /* 0x4A */)) {
      if(1){
        r=m=1;   // Line 418
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RALT | modCodes.VIRTUAL_KEY /* 0x4008 */, keyCodes.K_K /* 0x4B */)) {
      if(1){
        r=m=1;   // Line 419
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_1 /* 0x31 */)) {
      if(1){
        r=m=1;   // Line 422
        k.KDC(0,t);
        k.KO(-1,t,"꣡");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_2 /* 0x32 */)) {
      if(1){
        r=m=1;   // Line 423
        k.KDC(0,t);
        k.KO(-1,t,"꣢");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_3 /* 0x33 */)) {
      if(1){
        r=m=1;   // Line 424
        k.KDC(0,t);
        k.KO(-1,t,"꣣");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_4 /* 0x34 */)) {
      if(1){
        r=m=1;   // Line 425
        k.KDC(0,t);
        k.KO(-1,t,"꣤");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_5 /* 0x35 */)) {
      if(1){
        r=m=1;   // Line 426
        k.KDC(0,t);
        k.KO(-1,t,"꣥");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_6 /* 0x36 */)) {
      if(1){
        r=m=1;   // Line 427
        k.KDC(0,t);
        k.KO(-1,t,"꣦");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_7 /* 0x37 */)) {
      if(1){
        r=m=1;   // Line 428
        k.KDC(0,t);
        k.KO(-1,t,"꣧");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_8 /* 0x38 */)) {
      if(1){
        r=m=1;   // Line 429
        k.KDC(0,t);
        k.KO(-1,t,"꣢꣯");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_9 /* 0x39 */)) {
      if(1){
        r=m=1;   // Line 430
        k.KDC(0,t);
        k.KO(-1,t,"꣢꣫");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_0 /* 0x30 */)) {
      if(1){
        r=m=1;   // Line 431
        k.KDC(0,t);
        k.KO(-1,t,"꣣꣬");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_A /* 0x41 */)) {
      if(1){
        r=m=1;   // Line 432
        k.KDC(0,t);
        k.KO(-1,t,"꣪");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_K /* 0x4B */)) {
      if(1){
        r=m=1;   // Line 433
        k.KDC(0,t);
        k.KO(-1,t,"꣬");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_N /* 0x4E */)) {
      if(1){
        r=m=1;   // Line 434
        k.KDC(0,t);
        k.KO(-1,t,"꣭");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_P /* 0x50 */)) {
      if(1){
        r=m=1;   // Line 435
        k.KDC(0,t);
        k.KO(-1,t,"꣮");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_R /* 0x52 */)) {
      if(1){
        r=m=1;   // Line 436
        k.KDC(0,t);
        k.KO(-1,t,"꣯");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_S /* 0x53 */)) {
      if(1){
        r=m=1;   // Line 437
        k.KDC(0,t);
        k.KO(-1,t,"꣱");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_U /* 0x55 */)) {
      if(1){
        r=m=1;   // Line 438
        k.KDC(0,t);
        k.KO(-1,t,"꣫");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_V /* 0x56 */)) {
      if(1){
        r=m=1;   // Line 439
        k.KDC(0,t);
        k.KO(-1,t,"꣰");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_SLASH /* 0xBF */)) {
      if(1){
        r=m=1;   // Line 441
        k.KDC(0,t);
        k.KO(-1,t,"᳓");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_PERIOD /* 0xBE */)) {
      if(1){
        r=m=1;   // Line 442
        k.KDC(0,t);
        k.KO(-1,t,"᳑");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_COMMA /* 0xBC */)) {
      if(1){
        r=m=1;   // Line 443
        k.KDC(0,t);
        k.KO(-1,t,"᳐");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_BKSLASH /* 0xDC */)) {
      if(1){
        r=m=1;   // Line 444
        k.KDC(0,t);
        k.KO(-1,t,"꣼");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_RBRKT /* 0xDD */)) {
      if(1){
        r=m=1;   // Line 445
        k.KDC(0,t);
        k.KO(-1,t,"꣹");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_LBRKT /* 0xDB */)) {
      if(1){
        r=m=1;   // Line 446
        k.KDC(0,t);
        k.KO(-1,t,"꣸");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_QUOTE /* 0xDE */)) {
      if(1){
        r=m=1;   // Line 447
        k.KDC(0,t);
        k.KO(-1,t,"ꣻ");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_COLON /* 0xBA */)) {
      if(1){
        r=m=1;   // Line 448
        k.KDC(0,t);
        k.KO(-1,t,"꣺");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_Z /* 0x5A */)) {
      if(1){
        r=m=1;   // Line 449
        k.KDC(0,t);
        k.KO(-1,t,"᳸");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_X /* 0x58 */)) {
      if(1){
        r=m=1;   // Line 450
        k.KDC(0,t);
        k.KO(-1,t,"᳹");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_C /* 0x43 */)) {
      if(1){
        r=m=1;   // Line 451
        k.KDC(0,t);
        k.KO(-1,t,"᳒");
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_B /* 0x42 */)) {
      if(1){
        r=m=1;   // Line 454
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_D /* 0x44 */)) {
      if(1){
        r=m=1;   // Line 455
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_EQUAL /* 0xBB */)) {
      if(1){
        r=m=1;   // Line 456
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_E /* 0x45 */)) {
      if(1){
        r=m=1;   // Line 457
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_F /* 0x46 */)) {
      if(1){
        r=m=1;   // Line 458
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_G /* 0x47 */)) {
      if(1){
        r=m=1;   // Line 459
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_HYPHEN /* 0xBD */)) {
      if(1){
        r=m=1;   // Line 460
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_H /* 0x48 */)) {
      if(1){
        r=m=1;   // Line 461
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_I /* 0x49 */)) {
      if(1){
        r=m=1;   // Line 462
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_J /* 0x4A */)) {
      if(1){
        r=m=1;   // Line 463
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_O /* 0x4F */)) {
      if(1){
        r=m=1;   // Line 464
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_Q /* 0x51 */)) {
      if(1){
        r=m=1;   // Line 465
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_T /* 0x54 */)) {
      if(1){
        r=m=1;   // Line 466
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_W /* 0x57 */)) {
      if(1){
        r=m=1;   // Line 467
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.RCTRL | modCodes.VIRTUAL_KEY /* 0x4002 */, keyCodes.K_Y /* 0x59 */)) {
      if(1){
        r=m=1;   // Line 468
        k.KDC(0,t);
        k.KB(t);
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_SPACE /* 0x20 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t," ");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_1 /* 0x31 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़!");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"!");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,"!");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_QUOTE /* 0xDE */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़\"");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"\"");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,"\"");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_3 /* 0x33 */)) {
      if(1){
        r=m=1;   // Line 78
        k.KDC(0,t);
        k.KO(-1,t,"ॐ");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_4 /* 0x34 */)) {
      if(1){
        r=m=1;   // Line 79
        k.KDC(0,t);
        k.KO(-1,t,"₹");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_5 /* 0x35 */)) {
      if(1){
        r=m=1;   // Line 80
        k.KDC(0,t);
        k.KO(-1,t,"࿕");
      }
    }
      if(m) {}
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_7 /* 0x37 */)) {
      if(1){
        r=m=1;   // Line 82
        k.KDC(0,t);
        k.KO(-1,t,"☸");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_QUOTE /* 0xDE */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़'");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"'");
      }
      else if(k.KFCM(1,t,['\''])){
        r=m=1;   // Line 311
        k.KDC(1,t);
        k.KO(-1,t,"॑");
      }
      else if(k.KFCM(1,t,['॑'])){
        r=m=1;   // Line 312
        k.KDC(1,t);
        k.KO(-1,t,"᳚");
      }
      else if(k.KFCM(1,t,['᳚'])){
        r=m=1;   // Line 313
        k.KDC(1,t);
        k.KO(-1,t,"᳛");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,"'");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_9 /* 0x39 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़(");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"(");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,"(");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_0 /* 0x30 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़)");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,")");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,")");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_8 /* 0x38 */)) {
      if(1){
        r=m=1;   // Line 81
        k.KDC(0,t);
        k.KO(-1,t,"❀");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_EQUAL /* 0xBB */)) {
      if(1){
        r=m=1;   // Line 85
        k.KDC(0,t);
        k.KO(-1,t,"‍");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_COMMA /* 0xBC */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़,");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,",");
      }
      else if(k.KFCM(1,t,[','])){
        r=m=1;   // Line 95
        k.KDC(1,t);
        k.KO(-1,t,"॰");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,",");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_HYPHEN /* 0xBD */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़-");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"-");
      }
      else if(k.KFCM(1,t,['-'])){
        r=m=1;   // Line 101
        k.KDC(1,t);
        k.KO(-1,t,"–");
      }
      else if(k.KFCM(1,t,['–'])){
        r=m=1;   // Line 102
        k.KDC(1,t);
        k.KO(-1,t,"—");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,"-");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_PERIOD /* 0xBE */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़.");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,".");
      }
      else if(k.KFCM(1,t,['.'])){
        r=m=1;   // Line 97
        k.KDC(1,t);
        k.KO(-1,t,"।");
      }
      else if(k.KFCM(1,t,['।'])){
        r=m=1;   // Line 98
        k.KDC(1,t);
        k.KO(-1,t,"॥");
      }
      else if(k.KFCM(1,t,['॥'])){
        r=m=1;   // Line 99
        k.KDC(1,t);
        k.KO(-1,t,"…");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,".");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_SLASH /* 0xBF */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़/");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"/");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,"/");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_0 /* 0x30 */)) {
      if(1){
        r=m=1;   // Line 107
        k.KDC(0,t);
        k.KO(-1,t,"०");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_1 /* 0x31 */)) {
      if(1){
        r=m=1;   // Line 107
        k.KDC(0,t);
        k.KO(-1,t,"१");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_2 /* 0x32 */)) {
      if(1){
        r=m=1;   // Line 107
        k.KDC(0,t);
        k.KO(-1,t,"२");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_3 /* 0x33 */)) {
      if(1){
        r=m=1;   // Line 107
        k.KDC(0,t);
        k.KO(-1,t,"३");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_4 /* 0x34 */)) {
      if(1){
        r=m=1;   // Line 107
        k.KDC(0,t);
        k.KO(-1,t,"४");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_5 /* 0x35 */)) {
      if(1){
        r=m=1;   // Line 107
        k.KDC(0,t);
        k.KO(-1,t,"५");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_6 /* 0x36 */)) {
      if(1){
        r=m=1;   // Line 107
        k.KDC(0,t);
        k.KO(-1,t,"६");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_7 /* 0x37 */)) {
      if(1){
        r=m=1;   // Line 107
        k.KDC(0,t);
        k.KO(-1,t,"७");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_8 /* 0x38 */)) {
      if(1){
        r=m=1;   // Line 107
        k.KDC(0,t);
        k.KO(-1,t,"८");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_9 /* 0x39 */)) {
      if(1){
        r=m=1;   // Line 107
        k.KDC(0,t);
        k.KO(-1,t,"९");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_COLON /* 0xBA */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़:");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,":");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,":");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_COLON /* 0xBA */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़;");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,";");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,";");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_COMMA /* 0xBC */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़<");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"<");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,"<");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_EQUAL /* 0xBB */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़=");
      }
      else if(k.KFCM(4,t,['क','्','ष','्'])){
        r=m=1;   // Line 344
        k.KDC(4,t);
        k.KO(-1,t,"᳹");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"=");
      }
      else if(k.KFCM(2,t,['क','्'])){
        r=m=1;   // Line 337
        k.KDC(2,t);
        k.KO(-1,t,"꣬");
      }
      else if(k.KFCM(2,t,['न','्'])){
        r=m=1;   // Line 338
        k.KDC(2,t);
        k.KO(-1,t,"꣭");
      }
      else if(k.KFCM(2,t,['प','्'])){
        r=m=1;   // Line 339
        k.KDC(2,t);
        k.KO(-1,t,"꣮");
      }
      else if(k.KFCM(2,t,['र','्'])){
        r=m=1;   // Line 340
        k.KDC(2,t);
        k.KO(-1,t,"꣯");
      }
      else if(k.KFCM(2,t,['व','्'])){
        r=m=1;   // Line 341
        k.KDC(2,t);
        k.KO(-1,t,"꣰");
      }
      else if(k.KFCM(2,t,['स','्'])){
        r=m=1;   // Line 342
        k.KDC(2,t);
        k.KO(-1,t,"꣱");
      }
      else if(k.KFCM(2,t,['च','्'])){
        r=m=1;   // Line 345
        k.KDC(2,t);
        k.KO(-1,t,"᳒");
      }
      else if(k.KFCM(1,t,['='])){
        r=m=1;   // Line 316
        k.KDC(1,t);
        k.KO(-1,t,"ᳶ");
      }
      else if(k.KFCM(1,t,['१'])){
        r=m=1;   // Line 321
        k.KDC(1,t);
        k.KO(-1,t,"꣡");
      }
      else if(k.KFCM(1,t,['२'])){
        r=m=1;   // Line 322
        k.KDC(1,t);
        k.KO(-1,t,"꣢");
      }
      else if(k.KFCM(1,t,['३'])){
        r=m=1;   // Line 323
        k.KDC(1,t);
        k.KO(-1,t,"꣣");
      }
      else if(k.KFCM(1,t,['४'])){
        r=m=1;   // Line 324
        k.KDC(1,t);
        k.KO(-1,t,"꣤");
      }
      else if(k.KFCM(1,t,['५'])){
        r=m=1;   // Line 325
        k.KDC(1,t);
        k.KO(-1,t,"꣥");
      }
      else if(k.KFCM(1,t,['६'])){
        r=m=1;   // Line 326
        k.KDC(1,t);
        k.KO(-1,t,"꣦");
      }
      else if(k.KFCM(1,t,['७'])){
        r=m=1;   // Line 327
        k.KDC(1,t);
        k.KO(-1,t,"꣧");
      }
      else if(k.KFCM(1,t,['८'])){
        r=m=1;   // Line 328
        k.KDC(1,t);
        k.KO(-1,t,"꣢꣯");
      }
      else if(k.KFCM(1,t,['९'])){
        r=m=1;   // Line 329
        k.KDC(1,t);
        k.KO(-1,t,"꣢꣫");
      }
      else if(k.KFCM(1,t,['०'])){
        r=m=1;   // Line 330
        k.KDC(1,t);
        k.KO(-1,t,"꣣꣬");
      }
      else if(k.KFCM(1,t,['अ'])){
        r=m=1;   // Line 333
        k.KDC(1,t);
        k.KO(-1,t,"꣪");
      }
      else if(k.KFCM(1,t,['उ'])){
        r=m=1;   // Line 334
        k.KDC(1,t);
        k.KO(-1,t,"꣫");
      }
      else if(k.KFCM(1,t,['ॶ'])){
        r=m=1;   // Line 343
        k.KDC(1,t);
        k.KO(-1,t,"᳸");
      }
      else if(k.KFCM(1,t,['/'])){
        r=m=1;   // Line 346
        k.KDC(1,t);
        k.KO(-1,t,"᳓");
      }
      else if(k.KFCM(1,t,['.'])){
        r=m=1;   // Line 347
        k.KDC(1,t);
        k.KO(-1,t,"᳑");
      }
      else if(k.KFCM(1,t,[','])){
        r=m=1;   // Line 348
        k.KDC(1,t);
        k.KO(-1,t,"᳐");
      }
      else if(k.KFCM(1,t,['\\'])){
        r=m=1;   // Line 349
        k.KDC(1,t);
        k.KO(-1,t,"꣼");
      }
      else if(k.KFCM(1,t,['ऎ'])){
        r=m=1;   // Line 350
        k.KDC(1,t);
        k.KO(-1,t,"꣹");
      }
      else if(k.KFCM(1,t,['ऒ'])){
        r=m=1;   // Line 351
        k.KDC(1,t);
        k.KO(-1,t,"꣸");
      }
      else if(k.KFCM(1,t,['\''])){
        r=m=1;   // Line 352
        k.KDC(1,t);
        k.KO(-1,t,"ꣻ");
      }
      else if(k.KFCM(1,t,[';'])){
        r=m=1;   // Line 353
        k.KDC(1,t);
        k.KO(-1,t,"꣺");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,"=");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_PERIOD /* 0xBE */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़>");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,">");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,">");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_SLASH /* 0xBF */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़?");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"?");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,"?");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_2 /* 0x32 */)) {
      if(1){
        r=m=1;   // Line 93
        k.KDC(0,t);
        k.KO(-1,t,"@");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_A /* 0x41 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ा");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ा");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 111
        k.KDC(1,t);
        k.KO(-1,t,"ा");
      }
      else if(1){
        r=m=1;   // Line 151
        k.KDC(0,t);
        k.KO(-1,t,"आ");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_B /* 0x42 */)) {
      if(1){
        r=m=1;   // Line 191
        k.KDC(0,t);
        k.KO(-1,t,"भ्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_C /* 0x43 */)) {
      if(1){
        r=m=1;   // Line 193
        k.KDC(0,t);
        k.KO(-1,t,"छ्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_D /* 0x44 */)) {
      if(k.KFCM(1,t,['.'])){
        r=m=1;   // Line 233
        k.KDC(1,t);
        k.KO(-1,t,"ड़्");
      }
      else if(1){
        r=m=1;   // Line 195
        k.KDC(0,t);
        k.KO(-1,t,"ड्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_E /* 0x45 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ॅ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ॅ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 118
        k.KDC(1,t);
        k.KO(-1,t,"ॅ");
      }
      else if(1){
        r=m=1;   // Line 162
        k.KDC(0,t);
        k.KO(-1,t,"ऍ");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_F /* 0x46 */)) {
      if(1){
        r=m=1;   // Line 223
        k.KDC(0,t);
        k.KO(-1,t,"ङ्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_G /* 0x47 */)) {
      if(1){
        r=m=1;   // Line 197
        k.KDC(0,t);
        k.KO(-1,t,"घ्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_H /* 0x48 */)) {
      if(1){
        r=m=1;   // Line 185
        k.KDC(0,t);
        k.KO(-1,t,"ः");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_I /* 0x49 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ी");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ी");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 113
        k.KDC(1,t);
        k.KO(-1,t,"ी");
      }
      else if(1){
        r=m=1;   // Line 155
        k.KDC(0,t);
        k.KO(-1,t,"ई");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_J /* 0x4A */)) {
      if(1){
        r=m=1;   // Line 200
        k.KDC(0,t);
        k.KO(-1,t,"झ्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_K /* 0x4B */)) {
      if(1){
        r=m=1;   // Line 202
        k.KDC(0,t);
        k.KO(-1,t,"ख्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_L /* 0x4C */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ॢ");
      }
      else if(k.KFCM(2,t,['ळ','्'])){
        r=m=1;   // Line 174
        k.KDC(2,t);
        k.KO(-1,t,"ऌ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ॢ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 140
        k.KDC(1,t);
        k.KO(-1,t,"ॢ");
      }
      else if(k.KFCM(1,t,['ॢ'])){
        r=m=1;   // Line 141
        k.KDC(1,t);
        k.KO(-1,t,"ॢ");
      }
      else if(k.KFCM(1,t,['.'])){
        r=m=1;   // Line 238
        k.KDC(1,t);
        k.KO(-1,t,"ऴ्");
      }
      else if(1){
        r=m=1;   // Line 204
        k.KDC(0,t);
        k.KO(-1,t,"ळ्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_M /* 0x4D */)) {
      if(k.KFCM(1,t,['ं'])){
        r=m=1;   // Line 187
        k.KDC(1,t);
        k.KO(-1,t,"ँ");
      }
      else if(k.KFCM(1,t,['ऑ'])){
        r=m=1;   // Line 269
        k.KDC(1,t);
        k.KO(-1,t,"ॐ");
      }
      else if(1){
        r=m=1;   // Line 186
        k.KDC(0,t);
        k.KO(-1,t,"ं");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_N /* 0x4E */)) {
      if(k.KFCM(1,t,['~'])){
        r=m=1;   // Line 243
        k.KDC(1,t);
        k.KO(-1,t,"ङ्");
      }
      else if(1){
        r=m=1;   // Line 207
        k.KDC(0,t);
        k.KO(-1,t,"ण्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_O /* 0x4F */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ॉ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ॉ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 119
        k.KDC(1,t);
        k.KO(-1,t,"ॉ");
      }
      else if(1){
        r=m=1;   // Line 168
        k.KDC(0,t);
        k.KO(-1,t,"ऑ");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_P /* 0x50 */)) {
      if(1){
        r=m=1;   // Line 209
        k.KDC(0,t);
        k.KO(-1,t,"फ्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_Q /* 0x51 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ऻ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ऻ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 144
        k.KDC(1,t);
        k.KO(-1,t,"ऻ");
      }
      else if(1){
        r=m=1;   // Line 180
        k.KDC(0,t);
        k.KO(-1,t,"ॴ");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_R /* 0x52 */)) {
      if(k.KFCM(3,t,['र','्','‍'])){
        r=m=1;   // Line 172
        k.KDC(3,t);
        k.KO(-1,t,"ऋ");
      }
      else if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ृ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ृ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 137
        k.KDC(1,t);
        k.KO(-1,t,"ृ");
      }
      else if(k.KFCM(1,t,['ृ'])){
        r=m=1;   // Line 138
        k.KDC(1,t);
        k.KO(-1,t,"ृ");
      }
      else if(1){
        r=m=1;   // Line 211
        k.KDC(0,t);
        k.KO(-1,t,"र्‍");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_S /* 0x53 */)) {
      if(1){
        r=m=1;   // Line 213
        k.KDC(0,t);
        k.KO(-1,t,"ष्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_T /* 0x54 */)) {
      if(1){
        r=m=1;   // Line 215
        k.KDC(0,t);
        k.KO(-1,t,"ट्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_U /* 0x55 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ू");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ू");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 115
        k.KDC(1,t);
        k.KO(-1,t,"ू");
      }
      else if(1){
        r=m=1;   // Line 159
        k.KDC(0,t);
        k.KO(-1,t,"ऊ");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_V /* 0x56 */)) {
      if(1){
        r=m=1;   // Line 83
        k.KDC(0,t);
        k.KO(-1,t,"ऽ");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_W /* 0x57 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ॆ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ॆ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 122
        k.KDC(1,t);
        k.KO(-1,t,"ॆ");
      }
      else if(1){
        r=m=1;   // Line 176
        k.KDC(0,t);
        k.KO(-1,t,"ऄ");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_X /* 0x58 */)) {
      if(1){
        r=m=1;   // Line 224
        k.KDC(0,t);
        k.KO(-1,t,"ज्ञ्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_Y /* 0x59 */)) {
      if(k.KFCM(2,t,['घ','्'])){
        r=m=1;   // Line 266
        k.KDC(2,t);
        k.KO(-1,t,"ज्ञ्");
      }
      else if(1){
        r=m=1;   // Line 225
        k.KDC(0,t);
        k.KO(-1,t,"ञ्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_Z /* 0x5A */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ॗ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ॗ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 146
        k.KDC(1,t);
        k.KO(-1,t,"ॗ");
      }
      else if(1){
        r=m=1;   // Line 179
        k.KDC(0,t);
        k.KO(-1,t,"ॷ");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_LBRKT /* 0xDB */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ॆ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ॆ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 120
        k.KDC(1,t);
        k.KO(-1,t,"ॆ");
      }
      else if(1){
        r=m=1;   // Line 160
        k.KDC(0,t);
        k.KO(-1,t,"ऎ");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_BKSLASH /* 0xDC */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़\\");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"\\");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,"\\");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_RBRKT /* 0xDD */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ॊ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ॊ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 121
        k.KDC(1,t);
        k.KO(-1,t,"ॊ");
      }
      else if(1){
        r=m=1;   // Line 166
        k.KDC(0,t);
        k.KO(-1,t,"ऒ");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_6 /* 0x36 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 297
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़्");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 284
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"्");
      }
      else if(k.KFCM(1,t,['ृ'])){
        r=m=1;   // Line 139
        k.KDC(1,t);
        k.KO(-1,t,"ॄ");
      }
      else if(k.KFCM(1,t,['ॢ'])){
        r=m=1;   // Line 142
        k.KDC(1,t);
        k.KO(-1,t,"ॣ");
      }
      else if(k.KFCM(1,t,['ऋ'])){
        r=m=1;   // Line 173
        k.KDC(1,t);
        k.KO(-1,t,"ॠ");
      }
      else if(k.KFCM(1,t,['ऌ'])){
        r=m=1;   // Line 175
        k.KDC(1,t);
        k.KO(-1,t,"ॡ");
      }
      else if(k.KFCM(1,t,['ँ'])){
        r=m=1;   // Line 315
        k.KDC(1,t);
        k.KO(-1,t,"ꣳ");
      }
      else if(1){
        r=m=1;   // Line 86
        k.KDC(0,t);
        k.KO(-1,t,"्");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_HYPHEN /* 0xBD */)) {
      if(1){
        r=m=1;   // Line 84
        k.KDC(0,t);
        k.KO(-1,t,"‌");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_BKQUOTE /* 0xC0 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़`");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"`");
      }
      else if(k.KFCM(1,t,['`'])){
        r=m=1;   // Line 314
        k.KDC(1,t);
        k.KO(-1,t,"॒");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,"`");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_A /* 0x41 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 298
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़");
      }
      else if(k.KFCM(2,t,['@','a'])){
        r=m=1;   // Line 126
        k.KDC(2,t);
        k.KO(-1,t,"ा");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 285
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_NuktaVyanjana},'़'])){
        r=m=1;   // Line 299
        k.KDC(2,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ा");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 125
        k.KDC(1,t);
        k.KO(-1,t,"@a");
      }
      else if(k.KFCM(1,t,['अ'])){
        r=m=1;   // Line 150
        k.KDC(1,t);
        k.KO(-1,t,"आ");
      }
      else if(k.KFCM(1,t,[{t:'a',a:this.s_Vyanjana}])){
        r=m=1;   // Line 286
        k.KDC(1,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ा");
      }
      else if(1){
        r=m=1;   // Line 149
        k.KDC(0,t);
        k.KO(-1,t,"अ");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_B /* 0x42 */)) {
      if(1){
        r=m=1;   // Line 190
        k.KDC(0,t);
        k.KO(-1,t,"ब्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_C /* 0x43 */)) {
      if(k.KFCM(2,t,['न','्'])&&this.s_opt1===this.s28){
        r=m=1;   // Line 263
        k.KDC(2,t);
        k.KO(-1,t,"nc");
      }
      else if(1){
        r=m=1;   // Line 192
        k.KDC(0,t);
        k.KO(-1,t,"च्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_D /* 0x44 */)) {
      if(1){
        r=m=1;   // Line 194
        k.KDC(0,t);
        k.KO(-1,t,"द्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_E /* 0x45 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़े");
      }
      else if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','े'])){
        r=m=1;   // Line 303
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ी");
      }
      else if(k.KFCM(2,t,['@','a'])){
        r=m=1;   // Line 127
        k.KDC(2,t);
        k.KO(-1,t,"ॅ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"े");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'े'])){
        r=m=1;   // Line 290
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ी");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_NuktaVyanjana},'़'])){
        r=m=1;   // Line 299
        k.KDC(2,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ॅ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 116
        k.KDC(1,t);
        k.KO(-1,t,"े");
      }
      else if(k.KFCM(1,t,['े'])){
        r=m=1;   // Line 133
        k.KDC(1,t);
        k.KO(-1,t,"ी");
      }
      else if(k.KFCM(1,t,['ए'])){
        r=m=1;   // Line 154
        k.KDC(1,t);
        k.KO(-1,t,"ई");
      }
      else if(k.KFCM(1,t,['अ'])){
        r=m=1;   // Line 163
        k.KDC(1,t);
        k.KO(-1,t,"ऍ");
      }
      else if(k.KFCM(1,t,[{t:'a',a:this.s_Vyanjana}])){
        r=m=1;   // Line 286
        k.KDC(1,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ॅ");
      }
      else if(1){
        r=m=1;   // Line 161
        k.KDC(0,t);
        k.KO(-1,t,"ए");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_F /* 0x46 */)) {
      if(k.KFCM(1,t,['.'])){
        r=m=1;   // Line 235
        k.KDC(1,t);
        k.KO(-1,t,"फ़्");
      }
      else if(1){
        r=m=1;   // Line 220
        k.KDC(0,t);
        k.KO(-1,t,"फ्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_G /* 0x47 */)) {
      if(k.KFCM(2,t,['न','्'])&&this.s_opt1===this.s27){
        r=m=1;   // Line 262
        k.KDC(2,t);
        k.KO(-1,t,"ङ्ग्");
      }
      else if(k.KFCM(2,t,['ण','्'])){
        r=m=1;   // Line 268
        k.KDC(2,t);
        k.KO(-1,t,"ङ्");
      }
      else if(k.KFCM(1,t,['.'])){
        r=m=1;   // Line 230
        k.KDC(1,t);
        k.KO(-1,t,"ग़्");
      }
      else if(1){
        r=m=1;   // Line 196
        k.KDC(0,t);
        k.KO(-1,t,"ग्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_H /* 0x48 */)) {
      if(k.KFCM(3,t,['क','़','्'])){
        r=m=1;   // Line 229
        k.KDC(3,t);
        k.KO(-1,t,"ख़्");
      }
      else if(k.KFCM(3,t,['ज','़','्'])){
        r=m=1;   // Line 232
        k.KDC(3,t);
        k.KO(-1,t,"झ़्");
      }
      else if(k.KFCM(3,t,['ड','़','्'])){
        r=m=1;   // Line 234
        k.KDC(3,t);
        k.KO(-1,t,"ढ़्");
      }
      else if(k.KFCM(2,t,['n','c'])&&this.s_opt1===this.s29){
        r=m=1;   // Line 264
        k.KDC(2,t);
        k.KO(-1,t,"ञ्च्");
      }
      else if(k.KFCM(2,t,['क','्'])){
        r=m=1;   // Line 246
        k.KDC(2,t);
        k.KO(-1,t,"ख्");
      }
      else if(k.KFCM(2,t,['ग','्'])){
        r=m=1;   // Line 247
        k.KDC(2,t);
        k.KO(-1,t,"घ्");
      }
      else if(k.KFCM(2,t,['च','्'])){
        r=m=1;   // Line 248
        k.KDC(2,t);
        k.KO(-1,t,"च्");
      }
      else if(k.KFCM(2,t,['छ','्'])){
        r=m=1;   // Line 249
        k.KDC(2,t);
        k.KO(-1,t,"छ्");
      }
      else if(k.KFCM(2,t,['ज','्'])){
        r=m=1;   // Line 250
        k.KDC(2,t);
        k.KO(-1,t,"झ्");
      }
      else if(k.KFCM(2,t,['ट','्'])){
        r=m=1;   // Line 251
        k.KDC(2,t);
        k.KO(-1,t,"ठ्");
      }
      else if(k.KFCM(2,t,['ड','्'])){
        r=m=1;   // Line 252
        k.KDC(2,t);
        k.KO(-1,t,"ढ्");
      }
      else if(k.KFCM(2,t,['त','्'])){
        r=m=1;   // Line 253
        k.KDC(2,t);
        k.KO(-1,t,"थ्");
      }
      else if(k.KFCM(2,t,['द','्'])){
        r=m=1;   // Line 254
        k.KDC(2,t);
        k.KO(-1,t,"ध्");
      }
      else if(k.KFCM(2,t,['प','्'])){
        r=m=1;   // Line 255
        k.KDC(2,t);
        k.KO(-1,t,"फ्");
      }
      else if(k.KFCM(2,t,['ब','्'])){
        r=m=1;   // Line 256
        k.KDC(2,t);
        k.KO(-1,t,"भ्");
      }
      else if(k.KFCM(2,t,['ष','्'])){
        r=m=1;   // Line 257
        k.KDC(2,t);
        k.KO(-1,t,"ष्");
      }
      else if(k.KFCM(2,t,['स','्'])){
        r=m=1;   // Line 258
        k.KDC(2,t);
        k.KO(-1,t,"श्");
      }
      else if(1){
        r=m=1;   // Line 198
        k.KDC(0,t);
        k.KO(-1,t,"ह्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_I /* 0x49 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ि");
      }
      else if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','ि'])){
        r=m=1;   // Line 301
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ी");
      }
      else if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','े'])){
        r=m=1;   // Line 304
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ै");
      }
      else if(k.KFCM(2,t,['@','a'])){
        r=m=1;   // Line 128
        k.KDC(2,t);
        k.KO(-1,t,"ै");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ि");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'ि'])){
        r=m=1;   // Line 288
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ी");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'े'])){
        r=m=1;   // Line 291
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ै");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_NuktaVyanjana},'़'])){
        r=m=1;   // Line 299
        k.KDC(2,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ै");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 112
        k.KDC(1,t);
        k.KO(-1,t,"ि");
      }
      else if(k.KFCM(1,t,['ि'])){
        r=m=1;   // Line 131
        k.KDC(1,t);
        k.KO(-1,t,"ी");
      }
      else if(k.KFCM(1,t,['े'])){
        r=m=1;   // Line 134
        k.KDC(1,t);
        k.KO(-1,t,"ै");
      }
      else if(k.KFCM(1,t,['इ'])){
        r=m=1;   // Line 153
        k.KDC(1,t);
        k.KO(-1,t,"ई");
      }
      else if(k.KFCM(1,t,['अ'])){
        r=m=1;   // Line 164
        k.KDC(1,t);
        k.KO(-1,t,"ऐ");
      }
      else if(k.KFCM(1,t,['ए'])){
        r=m=1;   // Line 165
        k.KDC(1,t);
        k.KO(-1,t,"ऐ");
      }
      else if(k.KFCM(1,t,[{t:'a',a:this.s_Vyanjana}])){
        r=m=1;   // Line 286
        k.KDC(1,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ै");
      }
      else if(1){
        r=m=1;   // Line 152
        k.KDC(0,t);
        k.KO(-1,t,"इ");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_J /* 0x4A */)) {
      if(k.KFCM(2,t,['न','्'])&&this.s_opt1===this.s30){
        r=m=1;   // Line 265
        k.KDC(2,t);
        k.KO(-1,t,"ञ्ज्");
      }
      else if(k.KFCM(1,t,['.'])){
        r=m=1;   // Line 231
        k.KDC(1,t);
        k.KO(-1,t,"ज़्");
      }
      else if(1){
        r=m=1;   // Line 199
        k.KDC(0,t);
        k.KO(-1,t,"ज्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_K /* 0x4B */)) {
      if(k.KFCM(2,t,['न','्'])&&this.s_opt1===this.s26){
        r=m=1;   // Line 261
        k.KDC(2,t);
        k.KO(-1,t,"ङ्क्");
      }
      else if(k.KFCM(1,t,['.'])){
        r=m=1;   // Line 228
        k.KDC(1,t);
        k.KO(-1,t,"क़्");
      }
      else if(1){
        r=m=1;   // Line 201
        k.KDC(0,t);
        k.KO(-1,t,"क्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_L /* 0x4C */)) {
      if(1){
        r=m=1;   // Line 203
        k.KDC(0,t);
        k.KO(-1,t,"ल्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_M /* 0x4D */)) {
      if(1){
        r=m=1;   // Line 205
        k.KDC(0,t);
        k.KO(-1,t,"म्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_N /* 0x4E */)) {
      if(k.KFCM(1,t,['.'])){
        r=m=1;   // Line 236
        k.KDC(1,t);
        k.KO(-1,t,"ऩ्");
      }
      else if(k.KFCM(1,t,['~'])){
        r=m=1;   // Line 242
        k.KDC(1,t);
        k.KO(-1,t,"ञ्");
      }
      else if(1){
        r=m=1;   // Line 206
        k.KDC(0,t);
        k.KO(-1,t,"न्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_O /* 0x4F */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ो");
      }
      else if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','ो'])){
        r=m=1;   // Line 305
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ू");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ो");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'ो'])){
        r=m=1;   // Line 292
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ू");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 117
        k.KDC(1,t);
        k.KO(-1,t,"ो");
      }
      else if(k.KFCM(1,t,['ो'])){
        r=m=1;   // Line 135
        k.KDC(1,t);
        k.KO(-1,t,"ू");
      }
      else if(k.KFCM(1,t,['ओ'])){
        r=m=1;   // Line 158
        k.KDC(1,t);
        k.KO(-1,t,"ऊ");
      }
      else if(1){
        r=m=1;   // Line 167
        k.KDC(0,t);
        k.KO(-1,t,"ओ");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_P /* 0x50 */)) {
      if(1){
        r=m=1;   // Line 208
        k.KDC(0,t);
        k.KO(-1,t,"प्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_Q /* 0x51 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ऺ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ऺ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 143
        k.KDC(1,t);
        k.KO(-1,t,"ऺ");
      }
      else if(1){
        r=m=1;   // Line 182
        k.KDC(0,t);
        k.KO(-1,t,"ॳ");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_R /* 0x52 */)) {
      if(k.KFCM(2,t,['श','्'])){
        r=m=1;   // Line 267
        k.KDC(2,t);
        k.KO(-1,t,"श्र्");
      }
      else if(k.KFCM(1,t,['.'])){
        r=m=1;   // Line 237
        k.KDC(1,t);
        k.KO(-1,t,"ऱ्");
      }
      else if(1){
        r=m=1;   // Line 210
        k.KDC(0,t);
        k.KO(-1,t,"र्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_S /* 0x53 */)) {
      if(1){
        r=m=1;   // Line 212
        k.KDC(0,t);
        k.KO(-1,t,"स्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_T /* 0x54 */)) {
      if(1){
        r=m=1;   // Line 214
        k.KDC(0,t);
        k.KO(-1,t,"त्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_U /* 0x55 */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ु");
      }
      else if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','ु'])){
        r=m=1;   // Line 302
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ू");
      }
      else if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','ो'])){
        r=m=1;   // Line 306
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ौ");
      }
      else if(k.KFCM(2,t,['@','a'])){
        r=m=1;   // Line 129
        k.KDC(2,t);
        k.KO(-1,t,"ौ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ु");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'ु'])){
        r=m=1;   // Line 289
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ू");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'ो'])){
        r=m=1;   // Line 293
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ौ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_NuktaVyanjana},'़'])){
        r=m=1;   // Line 299
        k.KDC(2,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ौ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 114
        k.KDC(1,t);
        k.KO(-1,t,"ु");
      }
      else if(k.KFCM(1,t,['ु'])){
        r=m=1;   // Line 132
        k.KDC(1,t);
        k.KO(-1,t,"ू");
      }
      else if(k.KFCM(1,t,['ो'])){
        r=m=1;   // Line 136
        k.KDC(1,t);
        k.KO(-1,t,"ौ");
      }
      else if(k.KFCM(1,t,['उ'])){
        r=m=1;   // Line 157
        k.KDC(1,t);
        k.KO(-1,t,"ऊ");
      }
      else if(k.KFCM(1,t,['अ'])){
        r=m=1;   // Line 170
        k.KDC(1,t);
        k.KO(-1,t,"औ");
      }
      else if(k.KFCM(1,t,['ओ'])){
        r=m=1;   // Line 171
        k.KDC(1,t);
        k.KO(-1,t,"औ");
      }
      else if(k.KFCM(1,t,[{t:'a',a:this.s_Vyanjana}])){
        r=m=1;   // Line 286
        k.KDC(1,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ौ");
      }
      else if(1){
        r=m=1;   // Line 156
        k.KDC(0,t);
        k.KO(-1,t,"उ");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_V /* 0x56 */)) {
      if(1){
        r=m=1;   // Line 216
        k.KDC(0,t);
        k.KO(-1,t,"व्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_W /* 0x57 */)) {
      if(k.KFCM(2,t,['@','a'])){
        r=m=1;   // Line 130
        k.KDC(2,t);
        k.KO(-1,t,"ॉ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_NuktaVyanjana},'़'])){
        r=m=1;   // Line 299
        k.KDC(2,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ॉ");
      }
      else if(k.KFCM(1,t,['अ'])){
        r=m=1;   // Line 169
        k.KDC(1,t);
        k.KO(-1,t,"ऑ");
      }
      else if(k.KFCM(1,t,[{t:'a',a:this.s_Vyanjana}])){
        r=m=1;   // Line 286
        k.KDC(1,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ॉ");
      }
      else if(1){
        r=m=1;   // Line 217
        k.KDC(0,t);
        k.KO(-1,t,"व्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_X /* 0x58 */)) {
      if(1){
        r=m=1;   // Line 218
        k.KDC(0,t);
        k.KO(-1,t,"क्ष्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_Y /* 0x59 */)) {
      if(k.KFCM(1,t,['.'])){
        r=m=1;   // Line 239
        k.KDC(1,t);
        k.KO(-1,t,"य़्");
      }
      else if(1){
        r=m=1;   // Line 219
        k.KDC(0,t);
        k.KO(-1,t,"य्");
      }
    }
    else if(k.KKM(e, modCodes.VIRTUAL_KEY /* 0x4000 */, keyCodes.K_Z /* 0x5A */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ॖ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ॖ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 145
        k.KDC(1,t);
        k.KO(-1,t,"ॖ");
      }
      else if(1){
        r=m=1;   // Line 181
        k.KDC(0,t);
        k.KO(-1,t,"ॶ");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_LBRKT /* 0xDB */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ꣿ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ꣿ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 123
        k.KDC(1,t);
        k.KO(-1,t,"ꣿ");
      }
      else if(1){
        r=m=1;   // Line 177
        k.KDC(0,t);
        k.KO(-1,t,"ꣾ");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_BKSLASH /* 0xDC */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])&&this.s_opt1===this.s32){
        r=m=1;   // Line 295
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़|");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])&&this.s_opt1===this.s31){
        r=m=1;   // Line 282
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"|");
      }
      else if(1){
        r=m=1;   // Line 90
        k.KDC(0,t);
        k.KO(-1,t,"|");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_RBRKT /* 0xDD */)) {
      if(k.KFCM(3,t,[{t:'a',a:this.s_NuktaVyanjana},'़','्'])){
        r=m=1;   // Line 300
        k.KDC(3,t);
        k.KIO(-1,this.s_NuktaVyanjana,1,t);
        k.KO(-1,t,"़ॏ");
      }
      else if(k.KFCM(2,t,[{t:'a',a:this.s_Vyanjana},'्'])){
        r=m=1;   // Line 287
        k.KDC(2,t);
        k.KIO(-1,this.s_Vyanjana,1,t);
        k.KO(-1,t,"ॏ");
      }
      else if(k.KFCM(1,t,['@'])){
        r=m=1;   // Line 124
        k.KDC(1,t);
        k.KO(-1,t,"ॏ");
      }
      else if(1){
        r=m=1;   // Line 178
        k.KDC(0,t);
        k.KO(-1,t,"ॵ");
      }
    }
    else if(k.KKM(e, modCodes.SHIFT | modCodes.VIRTUAL_KEY /* 0x4010 */, keyCodes.K_BKQUOTE /* 0xC0 */)) {
      if(1){
        r=m=1;   // Line 92
        k.KDC(0,t);
        k.KO(-1,t,"~");
      }
    }
    return r;
  };
}
