"""Synthetic getItemList/getItemView test data; no captured provider responses."""
import json
def fixture(pid='88000001'):
    listing={'no':pid,'title':'SYNTHETIC listing','url':'https://domeggook.com/'+pid}
    payload={'basis':{'no':pid,'title':'SYNTHETIC product','status':'판매중'},'price':{'dome':'1+1000|10+900'},
        'qty':{'domeMoq':'2','domeUnit':'1','inventory':'30'},'thumb':{'large':'https://domeggook.com/image.jpg'},
        'deli':{'pay':'선결제','dome':{'type':'고정배송비','fee':'3000'},'feeExtra':{'jeju':'3000'}},
        'detail':{'manufacturer':'SYNTHETIC','model':'DEMO'},'desc':{'license':{'usable':'true'},'contents':{'item':'<p>SYNTHETIC description</p><img src="https://domeggook.com/detail.jpg">'}},
        'selectOpt':json.dumps({'type':'combination','data':{'00':{'name':'SYNTHETIC Red','dom':'1','hid':'0','domPrice':'100','qty':'8'},
            '01':{'name':'SYNTHETIC Blue','dom':'1','hid':'0','domPrice':'-100','qty':'0'}}})}
    return listing,payload
